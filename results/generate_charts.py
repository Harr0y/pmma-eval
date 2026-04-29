"""
生成实验结果可视化图表（用于 README 和论文）
依赖: pip install matplotlib pandas numpy
"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 中文字体配置
rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'PingFang SC', 'Heiti TC']
rcParams['axes.unicode_minus'] = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(SCRIPT_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# 加载汇总数据
with open(os.path.join(SCRIPT_DIR, 'experiment_summary.json')) as f:
    summary = json.load(f)

METHODS = ['no-mgmt', 'kanban', 'waterfall', 'scrum', 'evolutionary']
METHOD_LABELS = ['No-Mgmt', 'Kanban', 'Waterfall', 'Scrum', 'Evolutionary']
METHOD_COLORS = ['#95a5a6', '#3498db', '#2ecc71', '#f39c12', '#e74c3c']

TASKS = ['t1_todo_cli', 't2_blog', 't2_order', 't2_rbac', 't3_ecommerce']
TASK_LABELS = ['T1\nCLI待办', 'T2-1\n博客标签', 'T2-2\n订单管理', 'T2-3\nRBAC权限', 'T3\n电商+变更']


def build_matrix():
    """构建方法×任务通过率矩阵"""
    matrix = np.zeros((len(METHODS), len(TASKS)))
    for entry in summary:
        mi = METHODS.index(entry['method'])
        ti = TASKS.index(entry['task'])
        matrix[mi][ti] = entry['passed'] / entry['runs']
    return matrix


def chart_heatmap():
    """图1: 方法×任务通过率热力图"""
    matrix = build_matrix()

    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)

    ax.set_xticks(range(len(TASKS)))
    ax.set_xticklabels(TASK_LABELS, fontsize=11)
    ax.set_yticks(range(len(METHODS)))
    ax.set_yticklabels(METHOD_LABELS, fontsize=12)

    # 在每个格子上标注数值
    for i in range(len(METHODS)):
        for j in range(len(TASKS)):
            val = matrix[i][j]
            text = f'{int(val*100)}%'
            color = 'white' if val < 0.4 or val > 0.85 else 'black'
            ax.text(j, i, text, ha='center', va='center', fontsize=13, fontweight='bold', color=color)

    ax.set_title('PMMA-Eval: 方法×任务通过率 (Pass Rate)', fontsize=14, fontweight='bold', pad=15)
    fig.colorbar(im, ax=ax, label='通过率', shrink=0.8)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'heatmap.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✅ heatmap.png')


def chart_bar_comparison():
    """图2: 各方法总通过数对比柱状图"""
    method_totals = []
    for m in METHODS:
        total = sum(e['passed'] for e in summary if e['method'] == m)
        method_totals.append(total)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(METHOD_LABELS, method_totals, color=METHOD_COLORS, edgecolor='white', linewidth=1.5)

    for bar, val in zip(bars, method_totals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f'{val}/15', ha='center', va='bottom', fontsize=13, fontweight='bold')

    ax.set_ylabel('通过次数 (满分15)', fontsize=12)
    ax.set_title('PMMA-Eval: 各方法总通过数对比', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 17)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'bar_comparison.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✅ bar_comparison.png')


def chart_radar():
    """图3: 各方法分任务雷达图"""
    matrix = build_matrix()

    angles = np.linspace(0, 2 * np.pi, len(TASKS), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    for i, (method, color) in enumerate(zip(METHOD_LABELS, METHOD_COLORS)):
        values = matrix[i].tolist()
        values += values[:1]
        ax.plot(angles, values, 'o-', linewidth=2, label=method, color=color)
        ax.fill(angles, values, alpha=0.1, color=color)

    ax.set_thetagrids(np.degrees(angles[:-1]), TASK_LABELS)
    ax.set_ylim(0, 1.1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['25%', '50%', '75%', '100%'], fontsize=9)
    ax.set_title('PMMA-Eval: 方法-任务适配性雷达图', fontsize=14, fontweight='bold', pad=30)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'radar.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✅ radar.png')


def chart_cost_efficiency():
    """图4: 成本效率散点图 (Token消耗 vs 通过率)"""
    fig, ax = plt.subplots(figsize=(9, 6))

    for i, (method, color, label) in enumerate(zip(METHODS, METHOD_COLORS, METHOD_LABELS)):
        entries = [e for e in summary if e['method'] == method]
        avg_tokens = np.mean([e['avg_tokens'] for e in entries])
        total_passed = sum(e['passed'] for e in entries)
        ax.scatter(avg_tokens / 1000, total_passed, s=200, color=color, label=label,
                   edgecolors='white', linewidth=2, zorder=5)

    ax.set_xlabel('平均 Token 消耗 (千)', fontsize=12)
    ax.set_ylabel('总通过数 (满分15)', fontsize=12)
    ax.set_title('PMMA-Eval: 成本效率分析', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'cost_efficiency.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✅ cost_efficiency.png')


def chart_t3_detail():
    """图5: T3 电商+变更 各代详细结果（Evolutionary PM 亮点）"""
    # 读取 T3 evolutionary 的详细结果
    evo_t3_runs = []
    for run in [1, 2, 3]:
        path = os.path.join(SCRIPT_DIR, f'evolutionary_t3_ecommerce_{run}', 'result.json')
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                evo_t3_runs.append(data)

    if not evo_t3_runs:
        print('⚠ No T3 evolutionary data found, skipping T3 detail chart')
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for idx, (run_data, run_num) in enumerate(zip(evo_t3_runs, [1, 2, 3])):
        ax = axes[idx]
        results = run_data.get('results', [])
        # Extract ATU names and pass/fail
        atus = []
        passed = []
        for r in results:
            name = r.get('name', '')
            atus.append(name.replace('ATU-', ''))
            passed.append(1 if r.get('status') == 'PASSED' else 0)

        colors = ['#2ecc71' if p else '#e74c3c' for p in passed]
        ax.barh(range(len(atus)), [1]*len(atus), color=colors, edgecolor='white')
        ax.set_yticks(range(len(atus)))
        ax.set_yticklabels(atus, fontsize=9)
        ax.set_xlim(0, 1.5)
        ax.set_title(f'Run {run_num} ({sum(passed)}/{len(atus)} passed)', fontsize=11, fontweight='bold')
        ax.set_xticks([])
        for j, p in enumerate(passed):
            ax.text(0.5, j, '✓' if p else '✗', ha='center', va='center',
                    fontsize=14, fontweight='bold', color='white')

    fig.suptitle('Evolutionary PM × T3 电商系统: 各运行详细结果', fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 't3_evolutionary_detail.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✅ t3_evolutionary_detail.png')


if __name__ == '__main__':
    chart_heatmap()
    chart_bar_comparison()
    chart_radar()
    chart_cost_efficiency()
    chart_t3_detail()
    print(f'\n📁 图表已保存到 {CHARTS_DIR}/')
