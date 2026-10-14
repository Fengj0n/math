"""Application-only corrections checked against original question pages.

Exact source fingerprints bind a correction to the inspected transcription.
No upstream document, import payload or historical paper is rewritten.
"""
LAYOUTS = {
    'EXAM-M2-2025-19': {
        'hash':'38f68d6e32e0999b8a8aed4eb45177ec45c9281f1056f87ca2554d175ec9db3d',
        'page':'02_题库/阶段04_统一题库/原页/PDF-12/P018.png',
        'page_sha256':'7893e7458520cd73b378f455d5dc89c2dc9bad66ecda82ac14f21f0bfdf08f7e',
        'change':'原页解析明确由关于x的偏导积分，转写fx恢复偏导。',
        'symbols':{'fx':"f'_x"},
    },
    'EXAM-M2-2023-18': {
        'hash':'08901918205ba29fe4b5ae4bd1044969497c0c16d75b03c9153820e1fb78694a',
        'page':'02_题库/阶段04_统一题库/原页/PDF-16/P112.png',
        'page_sha256':'78c9f6cefe6773ee1f1f157a6ef8cbf8e0132d92290f8fab3155f042a19bfb84',
        'change':'原页确认二元函数极值任务；解析中的fx、fy、fxx、fxy、fyy恢复偏导下标。',
        'symbols':{'fx':"f'_x",'fy':"f'_y",'fxx':"f''_(xx)",'fxy':"f''_(xy)",'fyy':"f''_(yy)"},
    },
    'EXAM-M2-2024-05': {
        'hash':'fa73df8a9c85c06d6c72aebf92b7363b42ac1f146b7921f6950c07ff0854d4dc',
        'page':'02_题库/阶段04_统一题库/原页/PDF-11/P002.png',
        'page_sha256':'8f3f6aa366aadf32c0d1814be8c2fb8d226f8a3ab180bfeec4c95989c72daeaa',
        'change':'原页确认偏导连续性与可微性任务，解析fx恢复偏导符号。',
        'symbols':{'fx':"f'_x"},
    },
    'EXAM-M2-2024-12': {
        'hash':'ee39ed766244796702a201253284fecb6af98c1646f79ad6185be76d9dc3a8fe',
        'page':'02_题库/阶段04_统一题库/原页/PDF-11/P005.png',
        'page_sha256':'c48f5d232ffa6bf790bd16ec65531c7e701cde306437f9a19ad6ec72f8642847',
        'change':'原页含一阶、二阶偏导关系，解析的fx、fy恢复为偏导。',
        'symbols':{'fx':"f'_x",'fy':"f'_y"},
    },
    'LL27-M2-C04-JC-X-008': {
        'hash':'fcd378788589f4ca4019d3e79486424c13698f551ac6ff55804b7cefd268af9d',
        'page':'02_题库/阶段03_880分析/预览/Q048.png',
        'page_sha256':'d2d54064d10a58389e2693f37effb44f8c08e3b914110b4de6dc900ceb7b601a',
        'change':'原页确认二元函数极值任务；解析一、二阶偏导恢复下标。',
        'symbols':{'fx':"f'_x",'fy':"f'_y",'fxx':"f''_(xx)",'fxy':"f''_(xy)",'fyy':"f''_(yy)"},
    },
    'LL27-M2-C04-JC-J-001': {
        'hash':'3061cd3f44ce0c44e4e82b8c1fde655cee8177f581873e3e5b2e855304058465',
        'page':'02_题库/阶段03_880分析/预览/Q049.png',
        'page_sha256':'414ee2f3791629e293dd8df9b107a128050888a435d736fb073e6fbc19dc8c5b',
        'change':'原页确认u=f(x,y,z)的复合求导任务；链式法则答案fx、fy、fz恢复偏导下标。',
        'symbols':{'fx':"f'_x",'fy':"f'_y",'fz':"f'_z"},
    },
    'EXAM-M2-2023-03': {
        'hash': '369a145277de8aa976ae3d76b36ed14590073cf56d47d800275e30e3096e365e',
        'page': '02_题库/阶段04_统一题库/原页/PDF-16/P110.png',
        'page_sha256': '49454ecc9614dcfe198a4bbe71d2193d7cba0a20cece29c587680401f96496d4',
        'change': '原页确认xn、yn均为数列下标，恢复数列对象、递推范围及完整选项。',
        'symbols': {'xn':'x_n','yn':'y_n'},
        'stem': r'已知数列$\{x_n\}$、$\{y_n\}$满足：$x_1=y_1=\dfrac12$，$x_{n+1}=\sin x_n$，$y_{n+1}=y_n^2$（$n=1,2,\ldots$），则当$n\to\infty$时（　）。',
        'options': [r'$x_n$是$y_n$的高阶无穷小',r'$y_n$是$x_n$的高阶无穷小',r'$x_n$与$y_n$是等价无穷小',r'$x_n$与$y_n$是同阶但不等价的无穷小'],
    },
    'LL27-M2-C04-JC-X-001': {
        'hash': 'e49477793cf248e8576d28abb0101c78c44a72cb6cba28d24c30d04a566ac5fc',
        'page': '02_题库/阶段03_880分析/预览/Q047.png',
        'page_sha256': '86c80d7075d0e089785b71ed6199b1df6eedcf46b903fbd749b9dd5de9914239',
        'change': '原页确认fx、fy是偏导数而非乘积，补齐四项的评价点与完整设问。',
        'symbols': {'fx':"f'_x",'fy':"f'_y"},
        'stem': r'设$f(x,y)=\arcsin\sqrt{x^2+y^4}$，则下列选项正确的是（　）。',
        'options': [r"$f'_x(0,0)$存在，$f'_y(0,0)$不存在",r"$f'_x(0,0)$不存在，$f'_y(0,0)$存在",r"$f'_x(0,0)$不存在，$f'_y(0,0)$不存在",r"$f'_x(0,0)$存在，$f'_y(0,0)$存在"],
    },
    'LL27-M2-C04-JC-X-009': {
        'hash': '69471020334be900632ca31b35de76e8f25ae3f710dbd1c6fb7e27450f34ae0d',
        'page': '02_题库/阶段03_880分析/预览/Q048.png',
        'page_sha256': 'd2d54064d10a58389e2693f37effb44f8c08e3b914110b4de6dc900ceb7b601a',
        'change': '原页确认四项为偏导数关系，函数使用分式排版。',
        'symbols': {'fx':"f'_x",'fy':"f'_y"},
        'stem': r'设$f(x,y)=\dfrac{e^x}{x-y}$，则（　）。',
        'options': [r"$f'_x+f'_y=0$",r"$f'_x-f'_y=0$",r"$f'_x-f'_y=f$",r"$f'_x+f'_y=f$"],
    },
    'LL27-M2-C02-JC-X-015': {
        'hash': '37773008e7508e12e47562a17ea519739e38a9125cdf66f4d958822252ab2731',
        'page': '02_题库/阶段03_880分析/预览/Q018.png',
        'page_sha256': 'c32834785b827c35e9c248b8d978bb497b7cc71209140ea791a2882d9f419906',
        'change': '原页区分f的n阶导数与函数幂，四项恢复f(x)及普通幂指数，不将幂写成导数形式。',
        'stem': r"设$f(x)$有任意阶导数，且$f'(x)=f^2(x)$，则$f^{(n)}(x)=$（　）（$n>3$）。",
        'options': [r'$n!f^{n+1}(x)$',r'$nf^{n+1}(x)$',r'$f^{2n}(x)$',r'$n!f^{2n}(x)$'],
    },
    'EXAM-M2-2026-04': {
        'hash': '175dc20319d17a07edb590f5f6b3eac406c422938bd9398bd78652c6d81b01e2',
        'page': '02_题库/阶段04_统一题库/原页/PDF-13/P002.png',
        'page_sha256': '09413a9a0a9d49e2e8bcb36a12382af2b2171b47e65cd91b5935114ba58e8f41',
        'change': '依据原页恢复规范题面，四个积分明确排版；数学对象、选项及答案不变。',
        'stem': '设线密度为$1$的细直棒的两个端点分别位于点$(-1,0)$和点$(1,0)$处，质量为$m$的质点位于点$(0,1)$处，$G$为引力常量，则该细直棒对该质点的引力大小为（　）。',
        'options': [
            r'$\displaystyle\int_0^1\frac{2Gmx}{(x^2+1)^{1/2}}\,dx$',
            r'$\displaystyle\int_0^1\frac{2Gm}{(x^2+1)^{1/2}}\,dx$',
            r'$\displaystyle\int_0^1\frac{2Gmx}{(x^2+1)^{3/2}}\,dx$',
            r'$\displaystyle\int_0^1\frac{2Gm}{(x^2+1)^{3/2}}\,dx$'],
    },
    'EXAM-M2-2022-06': {
        'hash': '46d4b59a94185f8e9cad991780b78d3709132d124aa7eeb507ff325da58e2014',
        'page': '02_题库/阶段04_统一题库/原页/PDF-16/P108.png',
        'page_sha256': '18141486dc9f8867c2d616df655f74f069c7defe8d797d0bce674589449dc76a',
        'change': '依据原页补回数列对象与设问，恢复四项极限表述；转写的xn依原页明确为x_n。',
        'stem': r'已知数列$\{x_n\}$，其中$-\dfrac{\pi}{2}\le x_n\le\dfrac{\pi}{2}$，则（　）。',
        'options': [
            r'当$\displaystyle\lim_{n\to\infty}\cos(\sin x_n)$存在时，$\displaystyle\lim_{n\to\infty}x_n$存在。',
            r'当$\displaystyle\lim_{n\to\infty}\sin(\cos x_n)$存在时，$\displaystyle\lim_{n\to\infty}x_n$存在。',
            r'当$\displaystyle\lim_{n\to\infty}\cos(\sin x_n)$存在时，$\displaystyle\lim_{n\to\infty}\sin x_n$存在，但$\displaystyle\lim_{n\to\infty}x_n$不一定存在。',
            r'当$\displaystyle\lim_{n\to\infty}\sin(\cos x_n)$存在时，$\displaystyle\lim_{n\to\infty}\cos x_n$存在，但$\displaystyle\lim_{n\to\infty}x_n$不一定存在。'],
        'solution': r'因为$\cos x_n\in[0,1]$，正弦函数在$[0,1]$上严格单调且具有连续逆函数，所以$\sin(\cos x_n)$收敛能推出$\cos x_n$收敛。取$x_n=(-1)^n\pi/2$，则$\cos x_n=0$而$x_n$不收敛，反驳B；同时$\cos(\sin x_n)=\cos 1$恒定，但$\sin x_n=(-1)^n$不收敛，反驳A、C。因此选D。',
    },
}
