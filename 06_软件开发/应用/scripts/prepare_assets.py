"""Copy approved original demo and rules, preserving all upstream files."""
import json,pathlib,shutil
root=pathlib.Path(__file__).resolve().parents[2];project=root.parent;app=root/'应用';assets=app/'assets';assets.mkdir(exist_ok=True)
stem=json.loads((project/'04_模拟试卷/新卷02_过程/最终题面.json').read_text(encoding='utf-8'))
solutions=json.loads((project/'04_模拟试卷/新卷02_过程/最终解答.json').read_text(encoding='utf-8'))
answers={q['ID']:q for q in solutions['questions']}
assert len(answers)==22 and {q['ID'] for q in stem['questions']}==set(answers)
rows=[dict(answers[s['ID']],**s) for s in stem['questions']]
(assets/'demo.json').write_text(json.dumps({'schema_version':'math2-demo-1','nature':'项目已有原创练习，非官方真题','questions':rows},ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(project/'03_命题分析/阶段05_命题规则/规则阈值.json',assets/'rules.json')
shutil.copy2(app/'frontend/node_modules/katex/dist/katex.js',assets/'katex.cjs')
font=pathlib.Path('C:/Windows/Fonts/simsun.ttc')
print('demo:22; answers paired by ID; rules copied unchanged')
