fn main() {
    slint_build::compile("src/slint/widgets.slint").expect("Slint build failed");
    embed_resource::compile("app.rc", embed_resource::NONE);
}