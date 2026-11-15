"""Render shareable figures/report and a native Tableau workbook draft."""
from pathlib import Path
import base64
import copy
import json
import zipfile
import xml.etree.ElementTree as E
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def tableau_draft(root):
    folder=root/'tableau'; data=folder/'data'
    # Explicitly separate test headline data from validation exploration.
    pd.read_csv(data/'policy_summary.csv').query("split == 'test'").to_csv(data/'test_policy.csv',index=False)
    paired=pd.read_csv(data/'paired_comparisons.csv').query("split == 'test'").copy()
    paired['ci_width']=paired.normal_ci_high-paired.normal_ci_low
    paired.to_csv(data/'test_comparisons.csv',index=False)
    pd.read_csv(data/'selected_profiles.csv').query("split == 'validation'").to_csv(data/'validation_profiles.csv',index=False)
    wb=E.Element('workbook',{'version':'10.5','source-platform':'mac','original-version':'10.5','xmlns:user':'http://www.tableausoftware.com/xml/user'})
    dsroot=E.SubElement(wb,'datasources')
    params=E.SubElement(dsroot,'datasource',{'hasconnection':'false','inline':'true','name':'Parameters','version':'10.5'})
    for name,caption,value in [('Margin','假设单客贡献毛利',30),('ContactCost','假设单次触达成本',.5)]:
        col=E.SubElement(params,'column',{'name':f'[{name}]','caption':caption,'datatype':'real','role':'measure','type':'quantitative','param-domain-type':'range','value':str(value)})
        E.SubElement(col,'calculation',{'class':'tableau','formula':str(value)})
        E.SubElement(col,'range',{'min':'0','max':'1000','granularity':'.1'})
    definitions={}
    for name in ['overall_rates','test_policy','test_comparisons','contact_curve','uplift_calibration','validation_profiles']:
        df=pd.read_csv(data/f'{name}.csv')
        ds=E.SubElement(dsroot,'datasource',{'caption':name,'name':name,'inline':'true','version':'10.5'})
        conn=E.SubElement(ds,'connection',{'class':'textscan','directory':'data','filename':f'{name}.csv','server':'','password':''})
        rel=E.SubElement(conn,'relation',{'name':f'{name}.csv','table':f'[{name}#csv]','type':'table'})
        columns=E.SubElement(rel,'columns',{'character-set':'UTF-8','header':'yes','locale':'en_US','separator':',','text-qualifier':'"'})
        defs={}
        for i,c in enumerate(df.columns):
            dim = c in ['strategy','comparison','split','analysis_role','uplift_group','treatment_flg','contact_share']
            dt='string' if df[c].dtype.kind in 'OUS' else ('integer' if df[c].dtype.kind in 'iu' else 'real')
            E.SubElement(columns,'column',{'name':c,'datatype':dt,'ordinal':str(i)})
            defs[c]=E.SubElement(ds,'column',{'name':f'[{c}]','datatype':dt,'role':'dimension' if dim else 'measure','type':'nominal' if dim and c!='contact_share' else 'quantitative'})
        if name=='contact_curve':
            for key,field in [('net_value','gain_per_1000'),('net_low','ci_low'),('net_high','ci_high')]:
                defs[key]=E.SubElement(ds,'column',{'name':f'[{key}]','caption':{'net_value':'假设净收益','net_low':'假设净收益下限','net_high':'假设净收益上限'}[key],'datatype':'real','role':'measure','type':'quantitative'})
                E.SubElement(defs[key],'calculation',{'class':'tableau','formula':f'[{field}] * [Parameters].[Margin] - [contacts_per_1000] * [Parameters].[ContactCost]'})
        definitions[name]=defs
    worksheets=E.SubElement(wb,'worksheets')
    sheets=[]
    def sheet(title,source,row,col,mark='Bar',color=None,size=None,tooltip_fields=()):
        sheets.append(title)
        w=E.SubElement(worksheets,'worksheet',{'name':title})
        ft=E.SubElement(E.SubElement(E.SubElement(w,'layout-options'),'title'),'formatted-text')
        E.SubElement(ft,'run',{'bold':'true'}).text=title
        table=E.SubElement(w,'table');view=E.SubElement(table,'view')
        dss=E.SubElement(view,'datasources');E.SubElement(dss,'datasource',{'name':source,'caption':source})
        deps=E.SubElement(view,'datasource-dependencies',{'datasource':source})
        fields=list(dict.fromkeys([row,col]+([color] if color else [])+([size] if size else [])+list(tooltip_fields)))
        refs={}
        for f in fields:
            definition=definitions[source][f];deps.append(copy.deepcopy(definition))
            dim=definition.get('role')=='dimension';agg='none' if dim else 'avg';suffix='nk' if definition.get('type')=='nominal' else 'qk'
            name=f'[{agg}:{f}:{suffix}]';refs[f]=f'[{source}].{name}'
            E.SubElement(deps,'column-instance',{'column':f'[{f}]','derivation':'None' if dim else 'Avg','name':name,'pivot':'key','type':definition.get('type')})
        if source=='contact_curve' and 'net_value' in [row,col]:
            E.SubElement(dss,'datasource',{'name':'Parameters'})
            pdep=E.SubElement(view,'datasource-dependencies',{'datasource':'Parameters'})
            for c in params: pdep.append(copy.deepcopy(c))
        E.SubElement(view,'aggregation',{'value':'true'})
        pane=E.SubElement(E.SubElement(table,'panes'),'pane',{'selection-relaxation-option':'selection-relaxation-allow'})
        E.SubElement(pane,'view',{'breakdown':'auto'});E.SubElement(pane,'mark',{'class':mark})
        enc=E.SubElement(pane,'encodings')
        if color: E.SubElement(enc,'color',{'column':refs[color]})
        if size: E.SubElement(enc,'size',{'column':refs[size]})
        for f in tooltip_fields: E.SubElement(enc,'lod',{'column':refs[f]})
        tip=E.SubElement(E.SubElement(pane,'customized-tooltip',{'show-command-buttons':'false'}),'formatted-text')
        E.SubElement(tip,'run').text='\n'.join(f'{f}: <{refs[f]}>' for f in fields)
        E.SubElement(table,'rows').text=refs[row];E.SubElement(table,'cols').text=refs[col]
    sheet('01 两组购买率｜全样本描述','overall_rates','treatment_flg','purchase_rate',tooltip_fields=['customers','buyers'])
    sheet('02 策略收益｜既有测试集·20%触达','test_policy','strategy','gain_per_1000',tooltip_fields=['ci_low','ci_high','contacts_per_1000'])
    sheet('03 策略差异95%区间｜既有测试集','test_comparisons','comparison','normal_ci_low','GanttBar',size='ci_width',tooltip_fields=['estimate_per_1000','normal_ci_high'])
    sheet('04 触达比例曲线｜验证集探索','contact_curve','gain_per_1000','contact_share','Line',color='strategy',tooltip_fields=['ci_low','ci_high'])
    sheet('05 分组DR效果｜验证集','uplift_calibration','uplift_group','estimated_uplift_pp',tooltip_fields=['predicted_uplift_pp','ci_low_pp','ci_high_pp','customers'])
    sheet('06 选中客户消费画像｜验证集','validation_profiles','strategy','mean_history_spend',tooltip_fields=['mean_recency_days','mean_history_transactions'])
    sheet('07 净收益情景｜假设金额·验证集','contact_curve','net_value','contact_share','Line',color='strategy',tooltip_fields=['net_low','net_high'])
    dashboards=E.SubElement(wb,'dashboards');dash_names=[]
    groups=[('01 营销效果概览',sheets[:2]),('02 策略比较与校准',sheets[2:5]),('03 人群与成本情景',sheets[5:])]
    for title,children in groups:
        dash_names.append(title);d=E.SubElement(dashboards,'dashboard',{'name':title})
        E.SubElement(d,'size',{'maxheight':'900','maxwidth':'1200','minheight':'900','minwidth':'1200','sizing-mode':'fixed'})
        if title.startswith('03'):
            E.SubElement(E.SubElement(d,'datasources'),'datasource',{'name':'Parameters'})
            dep=E.SubElement(d,'datasource-dependencies',{'datasource':'Parameters'})
            for c in params: dep.append(copy.deepcopy(c))
        zones=E.SubElement(d,'zones')
        z=E.SubElement(zones,'zone',{'id':'1','type-v2':'text','x':'2000','y':'1000','w':'96000','h':'9000'})
        f=E.SubElement(z,'formatted-text');E.SubElement(f,'run',{'bold':'true','fontsize':'17'}).text=title+'｜RetailHero'
        E.SubElement(f,'run',{'fontsize':'10'}).text='\n离线估计；e=0.5 未核实；区间条件于固定模型。测试集此前已查看。'
        start=17000 if title.startswith('03') else 11000
        for i,name in enumerate(children):
            E.SubElement(zones,'zone',{'id':str(i+2),'name':name,'type-v2':'viz','show-title':'true','x':'2000','y':str(start+i*(85000-start)//len(children)),'w':'96000','h':str((85000-start)//len(children)-1000)})
        if title.startswith('03'):
            for i,p in enumerate(['Margin','ContactCost']):
                E.SubElement(zones,'zone',{'id':str(90+i),'type-v2':'paramctrl','param':f'[Parameters].[{p}]','x':str(2000+48000*i),'y':'10000','w':'46000','h':'6000'})
    windows=E.SubElement(wb,'windows',{'source-height':'900'})
    for title,children in groups:
        win=E.SubElement(windows,'window',{'class':'dashboard','name':title})
        views=E.SubElement(win,'viewpoints')
        for name in children: E.SubElement(E.SubElement(views,'viewpoint',{'name':name}),'zoom',{'type':'entire-view'})
    for name in sheets:
        w=E.SubElement(windows,'window',{'class':'worksheet','name':name});E.SubElement(w,'zoom',{'type':'entire-view'})
    E. indent(wb)
    path=folder/'RetailHero_营销决策_草稿.twb'
    E.ElementTree(wb).write(path,encoding='utf-8',xml_declaration=True)
    E.parse(path)
    with zipfile.ZipFile(folder/'RetailHero_营销决策_草稿.twbx','w',zipfile.ZIP_DEFLATED) as z:
        z.write(path,path.name)
        for p in sorted(data.glob('*.csv')):z.write(p,'data/'+p.name)


def present(root):
    report=root/'reports/portfolio';tables=report/'tables';figures=report/'figures'
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','figure.facecolor':'#f5f7fb','axes.facecolor':'white'})
    colors={'Uplift':'#087f8c','Response':'#d97848','Response_p1':'#bd9843','Random':'#6e7f91','RFM':'#9a80b7'}
    summary=pd.read_csv(tables/'policy_summary.csv').query("split == 'test'").sort_values('gain_per_1000')
    comp=pd.read_csv(tables/'paired_comparisons.csv');primary=comp.query("split == 'test' and comparison == 'Uplift - Response'").iloc[0]
    fig,axes=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    for i,r in enumerate(summary.itertuples()):
        axes[0].errorbar(r.gain_per_1000,i,xerr=[[r.gain_per_1000-r.ci_low],[r.ci_high-r.gain_per_1000]],fmt='o',color=colors[r.strategy],capsize=5,markersize=8)
    axes[0].set_yticks(range(len(summary)),summary.strategy);axes[0].axvline(0,color='#aaa',ls='--')
    axes[0].set(title='Policy value | 20% contacts',xlabel='Incremental buyers / 1,000 candidates')
    for i,(label,lo,hi) in enumerate([('Normal approximation',primary.normal_ci_low,primary.normal_ci_high),('Paired bootstrap',primary.bootstrap_ci_low,primary.bootstrap_ci_high)]):
        axes[1].errorbar(primary.estimate_per_1000,i,xerr=[[primary.estimate_per_1000-lo],[hi-primary.estimate_per_1000]],fmt='o',color='#087f8c',capsize=6)
        axes[1].text((lo+hi)/2,i+.15,f'[{lo:.2f}, {hi:.2f}]',ha='center')
    axes[1].set_yticks([0,1],['Normal approximation','Paired bootstrap']);axes[1].set_ylim(-.5,1.65)
    axes[1].axvline(0,color='#aaa',ls='--');axes[1].set(title='Uplift minus Response | 95% intervals',xlabel='Additional buyers / 1,000 candidates')
    fig.suptitle('Previously viewed test set | Assumed e = 0.5 | Fixed models',fontsize=14)
    fig.savefig(figures/'01_policy_uncertainty.png',dpi=160);plt.close(fig)

    curve=pd.read_csv(tables/'contact_curve.csv');cal=pd.read_csv(tables/'uplift_calibration.csv')
    fig,axes=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    for s,d in curve.groupby('strategy'):axes[0].plot(d.contact_share*100,d.gain_per_1000,label=s,color=colors[s],lw=2)
    axes[0].axvline(20,color='#aaa',ls=':');axes[0].set(title='Contact allocation',xlabel='Contact share (%)',ylabel='Incremental buyers / 1,000');axes[0].legend(fontsize=9)
    axes[1].plot(cal.uplift_group,cal.predicted_uplift_pp,'o--',color='#d97848',label='Predicted')
    axes[1].errorbar(cal.uplift_group,cal.estimated_uplift_pp,yerr=[cal.estimated_uplift_pp-cal.ci_low_pp,cal.ci_high_pp-cal.estimated_uplift_pp],fmt='o-',color='#087f8c',capsize=4,label='DR estimate, 95% CI')
    axes[1].set(title='Effect calibration',ylabel='Purchase probability difference (pp)');axes[1].legend(fontsize=9)
    fig.suptitle('Validation set | Exploratory diagnostics | Assumed e = 0.5',fontsize=14)
    fig.savefig(figures/'02_validation_diagnostics.png',dpi=160);plt.close(fig)

    scenario=pd.read_csv(tables/'cost_scenarios.csv').query('assumed_margin == 30 and assumed_contact_cost == 0.5')
    fig,ax=plt.subplots(figsize=(12,5),layout='constrained')
    for s,d in scenario.groupby('strategy'):ax.plot(d.contact_share*100,d.net_value_per_1000,color=colors[s],label=s,lw=2)
    d=scenario.query("strategy == 'Uplift'")
    ax.fill_between(d.contact_share*100,d.net_ci_low,d.net_ci_high,color=colors['Uplift'],alpha=.12,label='Uplift pointwise 95% CI')
    ax.axhline(0,color='#aaa',ls='--');ax.set(title='Hypothetical margin = 30 | Contact cost = 0.5 | Validation only',xlabel='Contact share (%)',ylabel='Hypothetical net value / 1,000 candidates');ax.legend(ncol=3,fontsize=9)
    fig.savefig(figures/'03_cost_scenario.png',dpi=160);plt.close(fig)
    imgs=[]
    for p in sorted(figures.glob('*.png')):
        imgs.append('<img alt="分析图表" src="data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()+'">')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>RetailHero 求职项目分析报告</title><style>body{margin:0;background:#f5f7fb;color:#1c2938;font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1100px;margin:auto;padding:48px 28px}h1{font-size:34px;line-height:1.3}h2{font-size:23px;margin-top:42px}.tag{color:#087f8c;letter-spacing:2px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:white;padding:20px;border-radius:12px}.number{font-size:32px;color:#087f8c;font-weight:700}img{width:100%;border-radius:12px;margin:18px 0}.note{border-left:4px solid #d97848;padding:12px 18px;background:#fff8ef}table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}@media(max-width:700px){.cards{grid-template-columns:1fr}h1{font-size:26px}}</style><main><div class="tag">RETAILHERO · 离线分析报告</div><h1>有限营销名额，如何带来更多新增购买？</h1><p>SQL 数据处理 → 客户增量响应建模 → 策略配对评价 → 成本情景与线上验证方案</p><div class="cards"><div class="card">有标签客户<div class="number">__CUSTOMER_COUNT__</div>客户为分析单位</div><div class="card">20% 触达，Uplift 离线收益<div class="number">__UPLIFT_GAIN__</div>新增购买客户／千名候选客户</div><div class="card">相对 Response 的额外收益<div class="number">__PAIRED_GAIN__</div>新增购买客户／千名候选客户</div></div><p class="note">结果依赖因果识别与 e=0.5 假设，非已实现的线上收益。测试集此前已查看；新增分析为探索性补充。以下图表为分析报告，不是 Tableau 软件渲染截图。</p>'''
    customer_count = int(pd.read_csv(tables/'overall_rates.csv').customers.sum())
    uplift_gain = float(summary.loc[summary.strategy.eq('Uplift'), 'gain_per_1000'].iloc[0])
    html = (html.replace('__CUSTOMER_COUNT__', f'{customer_count:,}')
                .replace('__UPLIFT_GAIN__', f'{uplift_gain:.2f}')
                .replace('__PAIRED_GAIN__', f'{primary.estimate_per_1000:.2f}'))
    run_path = root / 'run_metadata.json'
    if run_path.exists():
        mode = json.loads(run_path.read_text())['mode']
        origin = '合成数据演示，不是真实业务结果' if mode == 'synthetic_demo' else '真实数据的新划分实验，与历史结果不同'
        html += f'<p class="note">本报告数据：{origin}。</p>'
    html+='<h2>01 · 策略价值与不确定性</h2><p>配对 Bootstrap 使用同一批重采样客户计算策略差异；固定模型、分数及选人结果，不包含重新训练与策略选择的不确定性。</p>'+imgs[0]
    html+=f'<p>主比较的正态近似区间为 [{primary.normal_ci_low:.2f}, {primary.normal_ci_high:.2f}]；3,000 次配对 Bootstrap 百分位区间为 [{primary.bootstrap_ci_low:.2f}, {primary.bootstrap_ci_high:.2f}]。两者比较用于评估近似方法的敏感性，不构成新的独立验证。</p>'
    html+='<h2>02 · 触达比例与效果校准</h2><p>触达比例曲线只使用验证集，不将曲线最高点称为已经确认的最优预算。预测增量与分组估计存在差距，应区分选人能力和效果幅度的准确性。</p>'+imgs[1]
    html+='<h2>03 · 商业可行性情景</h2><p>假设净收益 = 新增购买人数 × 假设单客贡献毛利 − 触达人数 × 假设单次触达成本。金额使用一致的假设货币单位，非观测收入或利润。区间只传播购买效果的不确定性；不包含成本及毛利的不确定性。阴影为逐点区间，不能作为选择最优触达比例后的有效区间。</p>'+imgs[2]
    html+='<h2>04 · 下一步线上验证</h2><p>将客户随机分到 Uplift 策略组与 Response 策略组，各组均触达约 20%，对所有被分组客户计算固定观察窗口内的购买率；预先冻结模型、主指标与检验规则。若基线购买率假设为 62%、希望检测 0.5 个百分点的差异，双侧 α=0.05、检验功效 80% 的近似样本量见下表。</p>'
    sizes=pd.read_csv(tables/'experiment_sample_sizes.csv').query('assumed_baseline_rate == 0.62')
    html+=sizes[['mde_pp','customers_per_arm','total_customers']].rename(columns={'mde_pp':'最小可检测差异（百分点）','customers_per_arm':'每组客户数','total_customers':'合计客户数'}).to_html(index=False,border=0)
    html+='<p>这里只提供设计方案，未实施线上实验。正式执行前需确认发送与购买窗口、用户去重、触达成本、护栏指标和数据完备性。</p><h2>文件状态</h2><p>已生成 SQL 模块、客户策略分析表、汇总 CSV、统计区间、图表和实验方案。Tableau 包含三页看板草稿、七张工作表和成本参数；由于本机未安装 Tableau，尚未完成原生打开与交互验证，不应在简历中称为已发布看板。</p><p>数据来源：原项目 RetailHero 数据、固定划分和已有模型；方法和复现入口详见本次新增文档。</p></main></html>'
    (report/'项目展示报告.html').write_text(html)
    tableau_draft(root)
