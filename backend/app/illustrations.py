"""Original, deterministic editorial infographic. No model call or product-photo claim."""
from io import BytesIO
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import os
FONT=next((p for p in (os.environ.get('STUDIO_FONT_PATH',''),'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/System/Library/Fonts/PingFang.ttc','/System/Library/Fonts/STHeiti Medium.ttc') if p and Path(p).is_file()),'')

def render(title,report,kind='cover'):
    image=Image.new('RGB',(1200,700),'#f1f4e8');draw=ImageDraw.Draw(image)
    if not FONT:raise ValueError('STUDIO_CJK_FONT_REQUIRED')
    font=lambda size:ImageFont.truetype(FONT,size)
    draw.rounded_rectangle((30,30,1170,670),radius=28,fill='#ffffff')
    draw.text((76,64),'智启图文  /  资料图解',font=font(20),fill='#81916e')
    def wrap(text,max_width,f,max_lines):
        lines=['']
        for char in text:
            if draw.textlength(lines[-1]+char,font=f)>max_width:
                if len(lines)>=max_lines:
                    lines[-1]=lines[-1][:-1]+'…';break
                lines.append('')
            lines[-1]+=char
        return lines
    for i,line in enumerate(wrap(title,1030,font(37),2)):draw.text((76,113+i*54),line,font=font(37),fill='#31452d')
    if report.get('kind')=='news' and kind=='risks':
        topics=['核实适用条件','区分事实与推断','查看原始资料']
        subtitles=['留意发布时间、版本与地区','摘要和编辑分析不能替代实测','正文保留来源链接和资料时间']
    elif kind=='risks':
        topics=['交易前','现场验机','付款前']
        subtitles=['复核实时挂牌价、运费与库存','核对配置、账号锁、电池与维修','坚持平台担保，保存商品原链接']
    elif kind=='comparison' and report.get('groups'):
        groups=report['groups']
        group=groups[0]
        topics=['同配置样本','挂牌中位数','候选筛选']
        subtitles=[f"{group['sample_count']} 条近期样本 / {group['seller_count']} 个卖家",f"含运费 ¥{group['median_asking_price']:.2f}，不是成交价",'价格优势5%–35%，且无已识别风险']
    elif report.get('kind')=='news':
        topics=['发生了什么','适合谁使用','还有什么待核实']
        subtitles=['以已保存的公开资料为依据','把产品特性放进真实使用场景','摘要不能代替实测和完整原文']
    else:
        groups=report.get('groups',[])
        topics=['比较相同配置','看清价格依据','低价先查风险']
        subtitles=[f"本次 {report.get('sample_count',0)} 条商品记录",'含运费挂牌中位数，不是成交价','核对电池、维修、账号锁与验机']
        if len(groups)==1 and groups[0].get('median_asking_price') is not None:
            subtitles[1]=f"可比挂牌中位数 ¥{groups[0]['median_asking_price']:.2f}"
    for i,(topic,sub) in enumerate(zip(topics,subtitles)):
        x=76+i*352;draw.rounded_rectangle((x,280,x+322,520),radius=18,fill=['#e6ecda','#edf1e5','#f5eedf'][i])
        draw.text((x+22,303),f'0{i+1}',font=font(23),fill='#8b9b77')
        draw.text((x+22,356),topic,font=font(27),fill='#3d5736')
        for j,line in enumerate(wrap(sub,276,font(19),3)):draw.text((x+22,408+j*30),line,font=font(19),fill='#708061')
    draw.text((76,579),'原创编辑图解 · 非产品实拍 · 以正文原链接及观察时间为准',font=font(20),fill='#8a977b')
    output=BytesIO();image.save(output,'PNG',optimize=True);return output.getvalue()
