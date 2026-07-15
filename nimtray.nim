# nimtray_fixed.nim - Windows 系统托盘模块（基于 winim 重写）
# 依赖：nimble install winim
# 编译：nim c -d:release --app:gui nimtray_fixed.nim

import std/[os, tables, typedthreads]
import winim/lean          # 导入核心 Windows API helper
import winim/winstr        # 提供 +$、wstring 等字符串工具

# 必要的 Win32 headers（NOTIFYICONDATAW, Shell_NotifyIconW, CreateWindowExW 等）
import winim/inc/shellapi
import winim/inc/winuser
import winim/inc/windef

# ========== 常量定义 ==========
const
  WM_TRAYICON = WM_APP + 1
  TRAY_UID    = 1

# 固定类名（以宽字符字面量形式）
const
  classNameW = L"LightTrayWnd"

# ========== 托盘对象类型 ==========
type
  MenuCallback = proc () {.closure.}
  TrayObj* = object
    hwnd*: HWND
    hmenu*: HMENU
    iconPath*: string
    tooltip*: string
    onLeftClick*: MenuCallback
    running*: bool
    thread*: Thread[ptr TrayObj]
    callbackMsg*: UINT
    taskbarCreatedMsg*: UINT
    nextMenuId*: uint32
    menuCallbacks*: Table[uint32, MenuCallback]
  Tray* = ptr TrayObj

var gTray*: Tray = nil

# ========== 辅助函数 ==========
proc setWcharArray[N: static int](arr: var array[N, WCHAR], s: string) =
  ## 将字符串复制到固定长度宽字符数组（以 null 结尾）
  zeroMem(addr arr[0], N * 2)
  if s.len == 0: return
  let ws = +$s
  let n = min(ws.len, N - 1)
  for i in 0 ..< n:
    arr[i] = ws[i]

# ========== 窗口过程 ==========
proc trayWndProc(hwnd: HWND, msg: UINT, wParam: WPARAM, lParam: LPARAM): LRESULT {.stdcall.} =
  if gTray == nil:
    return DefWindowProcW(hwnd, msg, wParam, lParam)

  # 托盘图标回调消息
  if msg == gTray.callbackMsg:
    case lParam
    of WM_LBUTTONUP, WM_LBUTTONDBLCLK:
      if gTray.onLeftClick != nil:
        gTray.onLeftClick()
    of WM_RBUTTONUP:
      if gTray.hmenu != HMENU(0):
        var pt: POINT
        GetCursorPos(addr pt)
        SetForegroundWindow(hwnd)
        TrackPopupMenu(gTray.hmenu,
          TPM_LEFTALIGN or TPM_BOTTOMALIGN or TPM_RIGHTBUTTON,
          pt.x, pt.y, 0, hwnd, cast[LPRECT](nil))
        # Post a null message to allow the popup menu to disappear correctly
        PostMessageW(hwnd, WM_NULL, 0, 0)
    else: discard
    return 0

  # 菜单命令
  if msg == WM_COMMAND:
    let cmdId = wParam.uint32
    if gTray.menuCallbacks.len > 0 and gTray.menuCallbacks.hasKey(cmdId):
      let cb = gTray.menuCallbacks[cmdId]
      if cb != nil:
        cb()
    return 0

  # 任务栏重建（Explorer 重启）
  if msg == gTray.taskbarCreatedMsg:
    var nid: NOTIFYICONDATAW
    nid.cbSize = sizeof(NOTIFYICONDATAW).DWORD
    nid.hWnd = hwnd
    nid.uID = TRAY_UID
    nid.uFlags = NIF_MESSAGE or NIF_ICON or NIF_TIP
    nid.uCallbackMessage = gTray.callbackMsg
    if gTray.iconPath.len > 0:
      let wpath = +$gTray.iconPath
      nid.hIcon = LoadImageW(HINSTANCE(0), wpath, IMAGE_ICON, 0, 0,
                              LR_LOADFROMFILE or LR_DEFAULTSIZE)
    if nid.hIcon == HICON(0):
      nid.hIcon = LoadIconW(HINSTANCE(0), cast[LPCWSTR](IDI_APPLICATION))
    setWcharArray(nid.szTip, gTray.tooltip)
    discard Shell_NotifyIconW(NIM_ADD, addr nid)
    return 0

  if msg == WM_DESTROY:
    PostQuitMessage(0)
    return 0

  return DefWindowProcW(hwnd, msg, wParam, lParam)

# ========== 注册窗口类 ==========
proc registerTrayClass() =
  var wc: WNDCLASSW
  wc.lpfnWndProc = trayWndProc
  wc.lpszClassName = classNameW
  wc.hInstance = GetModuleHandleW(cast[LPCWSTR](nil))
  if RegisterClassW(addr wc) == 0:
    echo "[Tray] RegisterClass failed, error=", GetLastError()
  else:
    echo "[Tray] RegisterClass success"

# ========== 消息循环线程 ==========
proc trayMessageLoop(tray: ptr TrayObj) {.thread.} =
  echo "[TrayLoop] Thread start"

  # 创建隐藏窗口（使用常量类名）
  let hwnd = CreateWindowExW(0,
                             classNameW,
                             L"",
                             WS_OVERLAPPEDWINDOW,
                             0, 0, 1, 1,
                             HWND(0), HMENU(0), GetModuleHandleW(cast[LPCWSTR](nil)), cast[LPVOID](nil))
  if hwnd == HWND(0):
    echo "[TrayLoop] CreateWindowExW failed, error=", GetLastError()
    return
  tray.hwnd = hwnd
  echo "[TrayLoop] Hidden window created, hwnd=", cast[int](hwnd)

  # 添加托盘图标
  var nid: NOTIFYICONDATAW
  nid.cbSize = sizeof(NOTIFYICONDATAW).DWORD
  nid.hWnd = hwnd
  nid.uID = TRAY_UID
  nid.uFlags = NIF_MESSAGE or NIF_ICON or NIF_TIP
  nid.uCallbackMessage = tray.callbackMsg

  if tray.iconPath.len > 0:
    let wpath = +$tray.iconPath
    nid.hIcon = LoadImageW(HINSTANCE(0), wpath, IMAGE_ICON, 0, 0,
                           LR_LOADFROMFILE or LR_DEFAULTSIZE)
    if nid.hIcon == HICON(0):
      echo "[TrayLoop] Icon file load failed, using default"
  if nid.hIcon == HICON(0):
    nid.hIcon = LoadIconW(HINSTANCE(0), cast[LPCWSTR](IDI_APPLICATION))
    if nid.hIcon == HICON(0):
      echo "[TrayLoop] Default icon load failed, error=", GetLastError()
      return

  setWcharArray(nid.szTip, tray.tooltip)

  if Shell_NotifyIconW(NIM_ADD, addr nid) == 0:
    echo "[TrayLoop] NIM_ADD failed, error=", GetLastError()
    return
  echo "[TrayLoop] Icon added, entering message loop"

  # 消息循环
  var msg: MSG
  while true:
    let ret = GetMessageW(addr msg, HWND(0), 0, 0)
    if ret <= 0:
      break
    discard TranslateMessage(addr msg)
    discard DispatchMessageW(addr msg)

  # 清理：删除托盘图标
  var delNid: NOTIFYICONDATAW
  delNid.cbSize = sizeof(NOTIFYICONDATAW).DWORD
  delNid.hWnd = hwnd
  delNid.uID = TRAY_UID
  discard Shell_NotifyIconW(NIM_DELETE, addr delNid)
  echo "[TrayLoop] Icon removed, thread exiting"

# ========== 公共 API ==========

proc newTray*(iconPath: string = "", tooltip: string = "Tray"): Tray =
  discard SetProcessDPIAware()
  echo "[Tray] newTray"
  result = cast[Tray](alloc0(sizeof(TrayObj)))
  result.iconPath = iconPath
  result.tooltip = tooltip
  result.callbackMsg = WM_TRAYICON
  result.taskbarCreatedMsg = RegisterWindowMessageW(+$"TaskbarCreated")
  result.nextMenuId = 1000
  result.menuCallbacks = initTable[uint32, MenuCallback]()

  registerTrayClass()
  result.hmenu = CreatePopupMenu()
  if result.hmenu == HMENU(0):
    echo "[Tray] CreatePopupMenu failed, error=", GetLastError()
    dealloc(result)
    return nil

  gTray = result
  echo "[Tray] Object initialized (window not created yet)"

proc addMenuItem*(tray: Tray, text: string, callback: MenuCallback = nil): uint32 =
  if tray == nil: return 0
  if text == "-":
    AppendMenuW(tray.hmenu, MF_SEPARATOR, cast[UINT_PTR](0), cast[LPCWSTR](nil))
    return 0
  else:
    let id = tray.nextMenuId
    inc tray.nextMenuId
    let wtext = +$text
    AppendMenuW(tray.hmenu, MF_STRING, cast[UINT_PTR](id), wtext)
    if callback != nil:
      tray.menuCallbacks[id] = callback
    return id

proc modifyMenuItemText*(tray: Tray, menuId: uint32, newText: string) =
  if tray == nil or tray.hmenu == HMENU(0) or menuId == 0: return
  let wtext = +$newText
  let flags = MF_BYCOMMAND or MF_STRING
  discard ModifyMenuW(tray.hmenu, menuId.UINT, flags.UINT, cast[UINT_PTR](menuId), wtext)

proc setOnLeftClick*(tray: Tray, callback: MenuCallback) =
  if tray == nil: return
  tray.onLeftClick = callback

proc start*(tray: Tray) =
  if tray == nil or tray.running: return
  tray.running = true
  createThread(tray.thread, trayMessageLoop, tray)
  echo "[Tray] start() called, thread created"

proc stop*(tray: Tray) =
  if tray == nil or not tray.running: return
  tray.running = false
  if tray.hwnd != HWND(0):
    echo "[Tray] stop() posting WM_DESTROY"
    PostMessageW(tray.hwnd, WM_DESTROY, 0, 0)
  if tray.thread.running:
    echo "[Tray] stop() waiting for thread"
    joinThread(tray.thread)
    echo "[Tray] stop() thread ended"

proc destroyTray*(tray: var Tray) =
  if tray == nil: return
  echo "[Tray] destroyTray() begin"
  stop(tray)
  if tray.hmenu != HMENU(0):
    DestroyMenu(tray.hmenu)
    echo "[Tray] Menu destroyed"
  gTray = nil
  dealloc(tray)
  tray = nil
  echo "[Tray] destroyTray() done"