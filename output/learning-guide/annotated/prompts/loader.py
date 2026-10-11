# 导读·职责：按模板名读 jinja2 模板字符串
# 导读·层位：prompts 层;TurnPlanner 靠它拿模板
# 导读·约定：目录名写死 jinja2,文件名自动补 .jinja2 后缀
# prompts/loader.py
# pathlib 的 Path:面向对象拼路径,自带 read_text 读文件
from pathlib import Path


# 核心函数:输入模板名,输出模板字符串;失败就抛 OSError 由调用方兜底
def load_prompt(prompt_file_name: str) -> str:
    """
    加载模板文件
    :param prompt_file_name: 模板文件名
    :return: 模板字符串
    """
    # __file__ 是本文件路径;parents[0] 取其目录
    # 再拼 "jinja2/模板名.jinja2",得到模板文件的完整路径
    prompt_file_path = Path(__file__).resolve().parents[0] / "jinja2" / f"{prompt_file_name}.jinja2"
    # utf-8 读成纯文本字符串返回,交给 PromptTemplate 去解析渲染
    return prompt_file_path.read_text(encoding="utf-8")


# 自测入口:直接跑本文件时,读一个模板打印看看
if __name__ == '__main__':
    # 读 clarify_respond 模板(澄清话术用)来验证函数可用
    result = load_prompt("clarify_respond")
    print(result)
    # 打印类型:确认返回的确实是 str,下游 PromptTemplate 才收
    print(type(result))
