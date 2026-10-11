# itwwy/test/jinjia2/simple_template.py

from jinja2 import Template

# 模板文本
tpl = Template("用户：{{ name }}，积分：{{ score }}")
# 传入数据渲染
result = tpl.render(name="小明", score=99)
print(result)
# 输出：用户：小明，积分：99