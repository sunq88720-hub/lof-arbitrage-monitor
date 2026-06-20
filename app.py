import time
import pandas as pd
import requests
import streamlit as st

# ==================== 1. 配置活跃基金池 ====================
# 精选了场内成交量大、套利活跃的 LOF 基金
LOF_POOL = {
    "sh501018": {"name": "南方原油LOF", "is_capped": True},     # 长期暂停/严重限额
    "sz162411": {"name": "华宝油气LOF", "is_capped": False},
    "sz161125": {"name": "易方达标普500", "is_capped": False},
    "sz164906": {"name": "交银中证海外中国互联网", "is_capped": False},
    "sz160216": {"name": "国泰大宗商品", "is_capped": False},
    "sz164824": {"name": "华宝标普油气", "is_capped": False},
    "sh501005": {"name": "精准医疗LOF", "is_capped": False},
    "sz161725": {"name": "招商白酒LOF", "is_capped": False},
    "sz160621": {"name": "鹏华中证国防LOF", "is_capped": False},
    "sz161810": {"name": "银华内需精选LOF", "is_capped": False}
}

LOF_LIST = list(LOF_POOL.keys())
SINA_API = "https://hq.sinajs.cn/list={symbols}"
HEADERS = {
    "Referer": "https://finance.sina.com.cn/",
    "User-Agent": "Mozilla/5.0",
}

def parse_sina_response(text):
    result = {}
    for line in text.splitlines():
        if "hq_str_" not in line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        symbol = key.split("hq_str_", 1)[1].strip()
        fields = value.strip().strip(";").strip('"').split(",")
        result[symbol] = fields
    return result

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def fetch_sina(symbols):
    try:
        response = requests.get(
            SINA_API.format(symbols=",".join(symbols)),
            headers=HEADERS,
            timeout=8,
        )
        response.encoding = "gbk"
        response.raise_for_status()
        return parse_sina_response(response.text)
    except Exception:
        return {}

def get_action(premium_rate, is_capped):
    # 核心实战逻辑：如果基金暂停或限制申购，溢价套利就变成“虚假机会”，必须予以标注
    if premium_rate > 1.5:
        if is_capped:
            return "⚠️溢价(已限额/需底仓)"
        return "🔥溢价套利(场内卖出)"
    if premium_rate < -2.0:
        return "🍏折价套利(场内买入)"
    return "无机会"

@st.cache_data(ttl=8, show_spinner=False)
def load_data():
    iopv_symbols = [f"f_{symbol[2:]}" for symbol in LOF_LIST]
    market_data = fetch_sina(LOF_LIST)
    iopv_data = fetch_sina(iopv_symbols)

    rows = []
    for symbol in LOF_LIST:
        code = symbol[2:]
        quote = market_data.get(symbol, [])
        iopv_quote = iopv_data.get(f"f_{code}", [])

        if len(quote) < 10:
            continue

        # 优先使用我们自定义的更规范的中文名
        name = LOF_POOL[symbol]["name"]
        is_capped = LOF_POOL[symbol]["is_capped"]
        
        price = safe_float(quote[3])
        turnover = safe_float(quote[9]) # 新浪接口返回的是“元”

        iopv = 0.0
        for field in iopv_quote[1:8]:
            candidate = safe_float(field)
            if candidate > 0:
                iopv = candidate
                break

        # 过滤机制：剔除价格异常，或者日成交额小于 50,000 元的僵尸基（防流动性陷阱）
        if price <= 0 or iopv <= 0 or turnover < 50_000:
            continue

        premium_rate = (price - iopv) / iopv * 100
        rows.append(
            {
                "代码": code,
                "基金名称": name,
                "现价": price,
                "实时估值(IOPV)": iopv,
                "溢价率": premium_rate,
                "成交额(万元)": turnover / 10000.0, # 转换为万元展示，更适合手机阅读
                "限额情况": "暂停/大额限额" if is_capped else "正常申购",  # ✨新增这一行
                "套利指引": get_action(premium_rate, is_capped),

            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("溢价率", ascending=False)

# ==================== 2. Streamlit 页面渲染 ====================
st.set_page_config(page_title="专业 LOF 套利监控台", layout="wide")

# 移动端 10 秒自动刷新特效
st.markdown(
    """
    <script>
    setTimeout(function () {
        window.location.reload();
    }, 10000);
    </script>
    """,
    unsafe_allow_html=True,
)

st.title("📊 专业 LOF 实时套利监控盘")
st.caption("提示：溢价率 > 1.5% 触发溢价提示；折价率 < -2.0% 触发折价提示。每 10 秒全自动刷新。")

try:
    df = load_data()
except Exception as error:
    st.error(f"数据加载失败: {error}")
    st.stop()

if df.empty:
    st.warning("当前没有基金满足成交量过滤筛选条件。")
else:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "代码": st.column_config.TextColumn("代码"),
            "现价": st.column_config.NumberColumn("现价", format="%.3f"),
            "实时估值(IOPV)": st.column_config.NumberColumn("实时估值(IOPV)", format="%.3f"),
            "溢价率": st.column_config.NumberColumn("溢价率", format="%.2f%%"),
            "成交额(万元)": st.column_config.NumberColumn("成交额(万元)", format="%,.1f"),
            "限额情况": st.column_config.TextColumn("限额情况"), # ✨新增这一行
        },
    )

st.caption(f"🕒 最近更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")