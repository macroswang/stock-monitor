"""Standalone research figure; plotting dependencies are optional."""
import json
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from research.ma250_e2_diagnostics import OUT


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    r=json.loads((OUT/'results.json').read_text())
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname='/System/Library/Fonts/Supplemental/Arial Unicode.ttf').get_name()
    plt.rcParams.update({'font.family':font,'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,3,figsize=(12,6.2),sharey='row')
    panels=[('raw415','415只 · 未复权'),('raw_matched217','相同217只 · 未复权'),('qfq217','相同217只 · 前复权收益代理')]
    colors=['#475569','#8893a4','#247b58'];labels=['原规则','原规则＋现金','E2确认']
    for col,(name,title) in enumerate(panels):
        p=r['panels'][name];runs=[p['baseline'],p['cash_control']['result'],p['candidate']]
        for row,field in enumerate(('total','max_drawdown')):
            ax=axes[row,col];values=[v[field] for v in runs]
            ax.bar(range(3),values,color=colors,width=.62,zorder=3)
            ax.set_xticks(range(3),labels);ax.axhline(0,color='#9ba6b3',lw=.8)
            ax.grid(axis='y',alpha=.2,zorder=0)
            for i,value in enumerate(values):
                ax.annotate(f'{value:+.2f}%',(i,value),xytext=(0,6 if value>=0 else -15),textcoords='offset points',ha='center')
            ax.set_ylim((-12,30) if row==0 else (-26,1))
        axes[0,col].set_title(title,pad=14)
    axes[0,0].set_ylabel('全期组合总收益（%）');axes[1,0].set_ylabel('最大回撤（%）')
    fig.suptitle('年线信号：相近资金占用下的收益与回撤',x=.07,ha='left',fontsize=16,y=.97)
    fig.text(.07,.025,'现金对照：事后匹配E2平均资金占用，允许小数仓位，仅用于解释回撤来源。\n2019-01-02至2026-11-13；买卖各0.15%成本。既有历史日线回放，尚无新日期的独立验证。',fontsize=10,color='#475569')
    fig.subplots_adjust(left=.08,right=.985,top=.83,bottom=.17,wspace=.12,hspace=.32)
    fig.savefig(OUT/'cash-control.png',dpi=160,facecolor='white');plt.close(fig)


if __name__=='__main__':main()
