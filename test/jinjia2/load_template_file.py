# itwwy/test/jinjia2/load_template_file.py

from jinja2 import Environment, FileSystemLoader
import os

# 1. 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 创建 Jinja2 环境，设置模板搜索路径为当前目录
env = Environment(loader=FileSystemLoader(current_dir))

# 3. 加载模板文件
tpl = env.get_template('template.jinjia2')
print(type(tpl))

# 4. 准备渲染数据
data = {
    "question": "Jinja2和f-string有什么区别？",
    "docs": [
        {"content": "Jinja2是专业第三方模板引擎，支持循环、判断、外部文件"},
        {"content": "f-string是Python原生字符串格式化，仅适合简单文本"}
    ],
    "history": [
        {"role": "user", "content": "什么是Prompt模板？"},
        {"role": "assistant", "content": "用来动态生成发给大模型指令的文本工具"}
    ]
}

# 5. 渲染完整prompt字符串
full_prompt = tpl.render(**data)

# 打印最终生成的提示词
print(full_prompt)
