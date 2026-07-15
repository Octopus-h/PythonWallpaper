import std/[os, strutils, osproc, streams, logging, json, unicode]
import winim/lean
import winim/winstr
import nimtray
import times
import tinydialogs, parsetoml
import raylib, raygui

# 常量定义
const
    SPI_SETDESKWALLPAPER = 0x0014
    SPIF_SENDCHANGE = 0x0002
    config_file = "resources/config.json"
    ffplay_path = "resources/ffmpeg/ffplay.exe"
    py_env_path = "resources/pyenv/pythonw.exe"
    font_path = "resources/LXGWWenKaiLite-Light.ttf"
    icon_path = "resources/icons/icon.ico"
    info_text_path = "resources/text.toml"
    auto_start_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_registry_name = "PythonWallpaper"
    font_color = Color(r: 168, g: 141, b: 255, a: 255)

type
    TimeoutError* = object of CatchableError

# 全局变量定义
var
    tray_manager: Tray
    running: bool = true
    windowVisible: bool = false   # 控制窗口是否显示
    # 通信通道：托盘 -> 主线程
    cmdChan: Channel[string]
    currentProcess: Process
    font: Font
    file_path: string
    infoText: string
    auto_start_id: uint32

#====================辅助函数====================
# 在 JSON 对象中按路径设置值（若路径不存在则自动创建中间对象）
proc setJsonValue(root: var JsonNode, path: seq[string], value: JsonNode) =
    if path.len == 0: return
    var node = root
    for i in 0 ..< path.len - 1:
        let key = path[i]
        if not node.hasKey(key):
            node[key] = newJObject()
        node = node[key]
    # 最后一级键
    let lastKey = path[^1]
    node[lastKey] = value

# 通用 JSON 更新函数：文件不存在则创建，键存在则修改，否则追加
proc updateJson*(filePath: string, keyPath: string, value: JsonNode): bool =
    ## 更新 JSON 文件中的指定路径的值
    ## 若文件不存在，会自动创建；若路径不存在，会创建中间对象
    ## 返回是否成功
    try:
        # 读取现有文件或创建空对象
        var root: JsonNode
        if fileExists(filePath):
            try:
                root = json.parseFile(filePath)
                if root.kind != JObject:
                    root = newJObject()
            except:
                root = newJObject()   # 文件损坏则重新初始化
        else:
            root = newJObject()

        # 分割键路径
        let keys = keyPath.split('.')
        setJsonValue(root, keys, value)

        # 写回文件（格式化输出，缩进4空格）
        writeFile(filePath, root.pretty(4))
        return true
    except:
        return false

# 便捷重载：接受任意可序列化的值（自动转为 JsonNode）
proc updateJson*(filePath: string, keyPath: string, value: auto): bool =
    updateJson(filePath, keyPath, %*value)

proc selectFile(file_type: string, file_extension: string): string =
    # 构造过滤字符串，格式如： "*.txt;*.nim"
    let results = openFileDialog(
        title = "请选择一个文件",
        defaultPath = getCurrentDir() & "/resources/",
        filterPatterns = @[file_extension],
        singleFilterDescription = file_type
    )
    if results.len > 0:
        info "选择的文件是: ", results
        return results
    else:
        info "用户取消了选择"
        return ""   # 返回空字符串表示取消

proc getWorkerw(): HWND =
    ## 查找父窗口类名为 "Progman" 的 WorkerW 窗口
    ## 返回第一个符合条件的句柄，未找到返回 0
    when not defined(windows):
        return 0

    let progman = FindWindowW(L"Progman", nil)
    if progman == 0:
        error "[Error] 未找到 Progman 窗口"
        return 0

    # 触发 WorkerW 创建（可选，但保留以兼容部分系统）
    discard SendMessageTimeoutW(progman, 0x052C, 0, 0,
                                 SMTO_NORMAL, 1000, nil)

    var found: HWND = 0

    proc enumProc(hwnd: HWND, lParam: LPARAM): WINBOOL {.stdcall.} =
        let pFound = cast[ptr HWND](lParam)

        # 1. 检查当前窗口类名是否为 "WorkerW"
        var className: array[256, WCHAR]
        if GetClassNameW(hwnd, addr className[0], 256) == 0:
            return TRUE
        if $cast[LPWSTR](addr className[0]) != "WorkerW":
            return TRUE

        # 2. 获取父窗口并检查其类名是否为 "Progman"
        let parent = GetParent(hwnd)
        if parent == 0:
            return TRUE
        var parentClass: array[256, WCHAR]
        if GetClassNameW(parent, addr parentClass[0], 256) == 0:
            return TRUE
        if $cast[LPWSTR](addr parentClass[0]) == "Progman":
            pFound[] = hwnd
            return FALSE   # 找到即停止枚举
        return TRUE

    EnumWindows(enumProc, cast[LPARAM](addr found))

    if found == 0:
        warn "[Warning] 未找到父窗口为 Progman 的 WorkerW"
    else:
        info "[Info] 找到 WorkerW: 0x", toHex(cast[int](found), 8)

    return found

# 将指定窗口嵌入桌面底层（WorkerW）
proc setWindowsToWorkerw(hwnd: HWND): bool =
    ## 将窗口句柄对应的窗口嵌入 WorkerW，作为桌面壁纸层。
    ## 成功返回 true，失败返回 false。
    when not defined(windows):
        error "[Error] setWindowsToWorkerw 仅在 Windows 下有效"
        return false

    # 验证窗口句柄
    if hwnd == 0 or IsWindow(hwnd) == 0:
        error "[Error] 无效窗口句柄: 0x", toHex(hwnd, 8)
        return false

    # 获取 WorkerW
    let workerw = getWorkerw()
    if workerw == 0:
        return false

    # 1. 将窗口父级设为 WorkerW
    if SetParent(hwnd, workerw) == 0:
        error "[Error] SetParent 失败"
        return false

    # 2. 修改窗口样式：加上 WS_CHILD 和 WS_VISIBLE
    var style = GetWindowLongW(hwnd, GWL_STYLE)
    style = style or WS_CHILD or WS_VISIBLE
    if SetWindowLongW(hwnd, GWL_STYLE, style) == 0:
        warn "[Warning] 设置窗口样式可能失败"

    # 3. 移除窗口边框和标题栏（扩展样式）
    var exStyle = GetWindowLongW(hwnd, GWL_EXSTYLE)
    exStyle = exStyle and not (WS_EX_DLGMODALFRAME or WS_EX_WINDOWEDGE)
    if SetWindowLongW(hwnd, GWL_EXSTYLE, exStyle) == 0:
        warn "[Warning] 设置扩展样式可能失败"

    # 4. 获取屏幕尺寸并调整窗口位置
    let screenW = GetSystemMetrics(SM_CXSCREEN)
    let screenH = GetSystemMetrics(SM_CYSCREEN)
    if SetWindowPos(hwnd, 0, 0, 0, screenW, screenH,
                    SWP_NOZORDER or SWP_FRAMECHANGED) == 0:
        error "[Error] SetWindowPos 失败"
        return false

    # 5. 确保窗口可见
    ShowWindow(hwnd, SW_SHOW)

    info "[Success] 窗口 0x", toHex(hwnd, 8), " 已嵌入 WorkerW，尺寸：", screenW, "x", screenH
    return true

proc embedToWorkerw(target: HWND): HWND =
    ## 将窗口嵌入到桌面底层，成功返回句柄，失败返回 0
    when not defined(windows):
        return 0

    for attempt in 0..20:
        let results = setWindowsToWorkerw(target)
        if results:
            info "[Info] 窗口已通过标题嵌入桌面 WorkerW"
            return target
        else:
            warn "[Warning] 第 ", attempt+1, " 次找到窗口但嵌入失败，稍后重试..."
        sleep(50)  # 0.05 秒
    error "[Error] 通过标题查找并嵌入失败"
    return 0

proc getFirstLine(currentProcess: Process, timeoutMs: int = 3000): string =
    let startTime = times.getTime()

    while (times.getTime() - startTime).inMilliseconds < timeoutMs:
        try:
            let results = currentProcess.outputStream.readLine()
            return results
        except Exception as e:
            error "读取输出异常: ", e.msg

        sleep(50)
    return ""

proc changeWallpaper(path_casual: string, types_casual: string) = 
    var
        path = path_casual
        types = types_casual
        args: seq[string]
        run_app_path: string
        hwnd: HWND

    if fileExists(path) == false:
        warn "文件不存在，path:", path, "types:", types
        path = "resources/example.py"
        types = "py"

    case types
    of "py":
        run_app_path = py_env_path
        args = @[
            path
        ]
    of "exe":
        run_app_path = path
        args = @[]
    of "video":
        run_app_path = ffplay_path
        args = @[
            "-x", $1920,
            "-y", $1080,
            "-loop", "0",
            "-noborder",
            "-fs",
            "-window_title", "FFPLAY_WALLPAPER_" & extractFilename(path),
            "-an",
            "-loglevel", "quiet",
            "-i", path
        ]
    else:
        run_app_path = py_env_path
        args = @[
            "resources/example.py"
        ]

    info "创建新currentProcess, path:", run_app_path, " args:", args.join(" ")
    if currentProcess != nil and currentProcess.running:
        currentProcess.terminate()
        info "等待旧进程退出..."
        let start = times.getTime()
        while currentProcess.running and (times.getTime() - start).inMilliseconds < 3000:
            sleep(50)
        if currentProcess.running:
            warn "旧进程未响应，强制终止"
            currentProcess.kill()
        currentProcess.close()
    currentProcess = startProcess(
        command = run_app_path,
        args = args,
        options = {poUsePath, poDaemon, poStdErrToStdOut}
    )
    info "创建新currentProcess成功, path:", run_app_path, " args:", args.join(" ")

    case types
    of "py", "exe":
        let text = getFirstLine(currentProcess)
        if text != "":
            try:
                hwnd = cast[int](parseHexInt(text))
            except:
                hwnd = 0
        else:
            hwnd = 0
    of "video":
        info L("FFPLAY_WALLPAPER_" & extractFilename(path))
        let start = times.getTime()
        while (times.getTime() - start).inMilliseconds < 3000:
            sleep(50)
            hwnd = FindWindowW(nil, L("FFPLAY_WALLPAPER_" & extractFilename(path)))
            if hwnd != 0:
                break

    hwnd = embedToWorkerw(hwnd)

proc loadLastWallpaper() =
    if fileExists(config_file):
        try:
            let json = json.parseFile(config_file)
            let path = json["last_wallpaper_path"].getStr("")
            let typ = json["type"].getStr("")
            if path != "" and typ != "":
                info "恢复上次壁纸: ", path, " 类型: ", typ
                changeWallpaper(path, typ)
            else:
                info "配置文件缺少必要字段，跳过恢复"
                changeWallpaper("resources/example.py", "py")
                discard updateJson(config_file, "last_wallpaper_path", "resources/example.py")
                discard updateJson(config_file, "type", "py")
        except:
            warn "读取配置文件失败，跳过恢复"
            changeWallpaper("resources/example.py", "py")
    else:
        warn "配置文件不存在，跳过恢复"
        changeWallpaper("resources/example.py", "py")
        discard updateJson(config_file, "last_wallpaper_path", "resources/example.py")
        discard updateJson(config_file, "type", "py")

proc setAutoStart(enable: bool) =
    var hKey: HKEY
    if RegOpenKeyExW(HKEY_CURRENT_USER, newWideCString(auto_start_key),
                    0, KEY_WRITE, addr hKey) == ERROR_SUCCESS:
        if enable:
            let exePath = newWideCString(getAppFilename())
            let size = (exePath.len + 1) * 2  # 包括终止符的字节数
            discard RegSetValueExW(hKey, newWideCString(app_registry_name), 0, REG_SZ,
                       cast[ptr BYTE](addr exePath[0]), cast[DWORD](size))
        else:
            discard RegDeleteValueW(hKey, newWideCString(app_registry_name))
            RegCloseKey(hKey)
    else:
        warn "无法打开注册表键"

proc isAutoStartEnabled(): bool =
    var hKey: HKEY
    if RegOpenKeyExW(HKEY_CURRENT_USER, newWideCString(auto_start_key), 0, KEY_READ, addr hKey) == ERROR_SUCCESS:
        var buffer: array[1024, WCHAR]
        var bufSize: DWORD = DWORD(len(buffer))
        if RegQueryValueExW(hKey, newWideCString(app_registry_name), nil, nil, cast[LPBYTE](addr buffer), addr bufSize) == ERROR_SUCCESS:
            result = true
        RegCloseKey(hKey)

#===============================================

#====================gui函数====================
proc initFont() =
    if font.baseSize == 0:
        # 从 info.txt 读取文字
        if fileExists(info_text_path):
            try:
                info "文字读取成功"
                infoText = readFile(info_text_path).strip()
            except:
                warn "文字读取失败"

        var codepoints: seq[int32]
        # 提取所有文本中的 Unicode 码位
        for ch in runes(infoText):
            let cp = int32(ch)
            if cp notin codepoints:
                codepoints.add(cp)

        # **添加完整的 ASCII 可打印字符（英文、数字、标点）**
        for code in 0x20 .. 0x7E:
            if int32(code) notin codepoints:
                codepoints.add(int32(code))

        # 加载字体
        font = loadFont(font_path, 30, codepoints)
        if font.baseSize == 0:
            error "字体加载失败，使用默认字体"
            font = getFontDefault()

        guiSetFont(font)

proc aboutApp() =
    clearWindowState(flags(WindowHidden))

    var aboutText: string
    if fileExists(info_text_path):
        try:
            let toml = parsetoml.parseFile(info_text_path)
            aboutText = toml["about"].getStr("default text")
        except:
            warn "读取 TOML 文件失败，使用默认文本"
            aboutText = "默认关于文本"
    else:
        warn "TOML 配置文件不存在，使用默认文本"
        aboutText = "默认关于文本"

    # ---------- 准备文本行和尺寸 ----------
    let lines = aboutText.splitLines(keepEol = false)
    let fontSize: float32 = 30.0
    let spacing: float32 = 1.0

    # 计算每行高度和总高度
    var lineHeights: seq[float32]
    var totalHeight: float32 = 0.0
    var maxLineWidth: float32 = 0.0
    for line in lines:
        let size = measureText(font, line, fontSize, spacing)
        lineHeights.add(size.y)
        totalHeight += size.y
        if size.x > maxLineWidth:
            maxLineWidth = size.x

    # 面板区域（留出边距）
    let panelMargin: float32 = 20.0
    let panelWidth = float(getScreenWidth()) - 2 * panelMargin
    let panelHeight = float(getScreenHeight()) - 2 * panelMargin - 40   # 留出标题行

    # 内容区域（与面板同宽，高度为总文本高度）
    let contentRect = Rectangle(
        x: 0, y: 0,
        width: max(maxLineWidth, panelWidth),
        height: max(totalHeight, panelHeight)
    )

    var scroll = Vector2(x: 0, y: 0)   # 滚动偏移
    var view: Rectangle                # 可见区域（由 scrollPanel 返回）

    # ---------- 调整滚动条样式（可选） ----------
    guiSetStyle(Scrollbar, ScrollSliderSize, 20)   # 滑块宽度
    guiSetStyle(Scrollbar, ArrowsVisible, 1)       # 显示上下箭头

    # ---------- 主循环 ----------
    windowVisible = true
    while running and windowVisible:
        beginDrawing()
        clearBackground(RAYWHITE)

        # ---- 关闭按钮（右上角） ----
        
        let closeBtn = Rectangle(
            x: float(getScreenWidth()) - 110,
            y: 10,
            width: 100,
            height: 30
        )
        guiSetStyle(Default, TextSize, 30)
        if button(closeBtn, "关闭"):
            windowVisible = false
            setWindowState(flags(WindowHidden))

        # ----- 绘制标题 -----
        drawText(font, "关于", Vector2(x: panelMargin, y: 10), 30, 1, font_color)
    
        # ----- 滚动面板（参照官方示例） -----
        scrollPanel(
            bounds = Rectangle(
                x: panelMargin,
                y: 50,
                width: panelWidth,
                height: panelHeight
            ),
            text = "",
            content = contentRect,
            scroll = scroll,
            view = view
        )

        # ----- 在 view 区域内绘制文本（应用滚动偏移） -----
        beginScissorMode(
            int32(view.x), int32(view.y),
            int32(view.width), int32(view.height)
        )
        var yPos: float32 = 0.0
        for i, line in lines:
            let drawX = view.x + scroll.x
            let drawY = view.y + yPos + scroll.y
            # 仅绘制在可见区域内的行
            if drawY + lineHeights[i] > 0 and drawY < view.height:
                drawText(
                    font, line,
                    Vector2(x: drawX, y: drawY),
                    fontSize, spacing, font_color
                )
            yPos += lineHeights[i]
        endScissorMode()
        endDrawing()

#===============================================

#====================回调函数====================
proc selectPy() = 
    file_path = selectFile("Python文件", "*.py")
    if file_path == "":
        return
    cmdChan.send("py")
    let now = times.getTime().format("yyyy-MM-dd HH:mm:ss")
    discard updateJson(config_file, "last_wallpaper_path", file_path)
    discard updateJson(config_file, "type", "py")
    discard updateJson(config_file, "update_time", now)

proc selectVideo() = 
    file_path = selectFile("MP4文件", "*.mp4")
    if file_path == "":
        return
    cmdChan.send("video")
    let now = times.getTime().format("yyyy-MM-dd HH:mm:ss")
    discard updateJson(config_file, "last_wallpaper_path", file_path)
    discard updateJson(config_file, "type", "video")
    discard updateJson(config_file, "update_time", now)

proc selectEXE() = 
    file_path = selectFile("可执行文件", "*.exe")
    if file_path == "":
        return
    cmdChan.send("exe")
    let now = times.getTime().format("yyyy-MM-dd HH:mm:ss")
    discard updateJson(config_file, "last_wallpaper_path", file_path)
    discard updateJson(config_file, "type", "exe")
    discard updateJson(config_file, "update_time", now)

proc showAbout() =
    cmdChan.send("about")

proc autoStart() = 
    cmdChan.send("autoStart")

proc onExit() =
    running = false
    cmdChan.send("quit")
#===============================================

proc initLogging() =
    # 创建控制台日志处理器（输出到 stdout）
    let consoleLogger = newConsoleLogger(
        levelThreshold = lvlAll,
        fmtStr = verboseFmtStr
    )
    # 创建文件日志处理器（追加写入 lastlog.log）
    let fileLogger = newFileLogger(
        filename = "lastlog.log",
        mode = fmAppend,
        levelThreshold = lvlAll,
        fmtStr = verboseFmtStr
    )
    addHandler(consoleLogger)
    addHandler(fileLogger)
    # 设置全局日志过滤级别（全部记录）
    setLogFilter(lvlAll)

proc main() =
    # 初始化日志系统
    initLogging()

    # ----- 初始化 raylib 窗口（隐藏） -----
    setConfigFlags(flags(Msaa4xHint, WindowHidden, WindowUndecorated))
    initWindow(800, 600, "壁纸切换工具")
    defer:
        closeWindow()
    setWindowIcon(loadImage("resources/icons/icon.png"))
    setTargetFPS(60)
    initFont()    # 加载全局字体（只一次）

    cmdChan.open()

    # 创建托盘对象
    tray_manager = newTray(icon_path, "PythonWallpaper")
    auto_start_id = tray_manager.addMenuItem(if isAutoStartEnabled(): "开机自启✔" else: "开机自启", autoStart)
    discard tray_manager.addMenuItem("-")                # 分隔线
    discard tray_manager.addMenuItem("切换壁纸(Python)", selectPy)
    discard tray_manager.addMenuItem("切换壁纸(exe)", selectEXE)
    discard tray_manager.addMenuItem("切换壁纸(mp4)", selectVideo)
    discard tray_manager.addMenuItem("-")                # 分隔线
    discard tray_manager.addMenuItem("关于", showAbout)
    discard tray_manager.addMenuItem("-")                # 分隔线
    discard tray_manager.addMenuItem("退出", onExit)
    tray_manager.setOnLeftClick(nil)
    tray_manager.start()                         # 启动托盘线程

    loadLastWallpaper()

    while running:
        # 处理托盘发来的命令
        var (hasCmd, cmd) = cmdChan.tryRecv()
        if hasCmd:
            info cmd
            case cmd
            of "quit":
                running = false
                break
            of "py", "exe", "video":
                changeWallpaper(file_path, cmd)
            of "about":
                aboutApp()
            of "autoStart":
                if isAutoStartEnabled():
                    setAutoStart(false)
                else:
                    setAutoStart(true)
                tray_manager.modifyMenuItemText(auto_start_id, if isAutoStartEnabled(): "开机自启✔" else: "开机自启")
            else:
                warn "未知命令:", cmd
        sleep(50)

    # 清理
    if currentProcess != nil and currentProcess.running:
        currentProcess.terminate()
        info "等待currentProcess退出..."
        let start = times.getTime()
        while currentProcess.running and (times.getTime() - start).inMilliseconds < 3000:
            sleep(50)
        if currentProcess.running:
            warn "currentProcess未响应，强制终止"
            currentProcess.kill()
        currentProcess.close()

    tray_manager.destroyTray()    # 自动停止线程、删除图标、释放资源
    info "托盘退出"
    cmdChan.close()

    discard SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, nil, SPIF_SENDCHANGE)

try:
    main()
except Exception as e:
    error("程序异常终止: ", e.msg)
    error(e.getStackTrace())
    when defined(debug):
        discard readLine(stdin)