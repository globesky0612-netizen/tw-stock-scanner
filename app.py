import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# ==========================================
# 網頁基本設定
# ==========================================
st.set_page_config(page_title="台股籌碼爆量掃描器", page_icon="📈", layout="wide")

# ==========================================
# 資料抓取核心函式 (加入快取避免重複抓取)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_daily_data(date_str):
    """
    抓取籌碼(T86)與成交量(MI_INDEX) - 新舊版 API 雙重解析與容錯版
    """
    # 升級版 Headers 偽裝成真實瀏覽器，降低被證交所封鎖的機率
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive"
    }
    
    url_t86 = f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
    url_mi = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALLBUT0999"
    
    try:
        # 1. 抓取法人籌碼
        res_t86 = requests.get(url_t86, headers=headers, timeout=10) 
        data_t86 = res_t86.json()
        
        if data_t86.get('stat') != 'OK':
            return None # 無交易資料 (可能為假日或未公佈)
            
        df_t86 = pd.DataFrame(data_t86['data'], columns=data_t86['fields'])
        
        foreign_col, trust_col = None, None
        for col in df_t86.columns:
            if '投信買賣超' in col: 
                trust_col = col
            elif '買賣超' in col and ('外資' in col or '外陸資' in col) and '自營商買賣超' not in col:
                foreign_col = col
                
        if not foreign_col or not trust_col:
            return None # 找不到籌碼欄位
                
        df_t86 = df_t86[['證券代號', '證券名稱', foreign_col, trust_col]]
        df_t86.columns = ['代號', '名稱', '外資買賣超', '投信買賣超']
        # 轉成字串清理逗號後再轉回浮點數
        df_t86['外資買賣超'] = df_t86['外資買賣超'].astype(str).str.replace(',', '').astype(float)
        df_t86['投信買賣超'] = df_t86['投信買賣超'].astype(str).str.replace(',', '').astype(float)

        # 延遲休息，避免連續請求被證交所阻擋
        time.sleep(8) 

        # 2. 抓取成交量
        res_mi = requests.get(url_mi, headers=headers, timeout=10)
        data_mi = res_mi.json()
        
        vol_df = None
        if data_mi.get('stat') == 'OK':
            # 解析新版表格
            if 'tables' in data_mi:
                for table in data_mi['tables']:
                    fields = table.get('fields', [])
                    code_col = next((c for c in fields if '證券代號' in c or '代號' in c), None)
                    vol_col = next((c for c in fields if '成交股數' in c or '成交量' in c), None)
                    if code_col and vol_col:
                        vol_df = pd.DataFrame(table.get('data', []), columns=fields)
                        vol_df = vol_df[[code_col, vol_col]]
                        vol_df.columns = ['代號', '成交量']
                        break
            # 解析舊版表格
            if vol_df is None:
                for key, value in data_mi.items():
                    if 'fields' in key and isinstance(value, list):
                        code_col = next((c for c in value if '證券代號' in c or '代號' in c), None)
                        vol_col = next((c for c in value if '成交股數' in c or '成交量' in c), None)
                        if code_col and vol_col:
                            data_key = key.replace('fields', 'data')
                            actual_data = data_mi.get(data_key, data_mi.get('data', []))
                            if actual_data:
                                vol_df = pd.DataFrame(actual_data, columns=value)
                                vol_df = vol_df[[code_col, vol_col]]
                                vol_df.columns = ['代號', '成交量']
                                break
                            
        if vol_df is not None:
            vol_df['成交量'] = vol_df['成交量'].astype(str).str.replace(',', '').astype(float)
            daily_df = pd.merge(df_t86, vol_df, on='代號', how='left')
            daily_df['日期'] = date_str
            return daily_df
        else:
            df_t86['成交量'] = 0.0  
            df_t86['日期'] = date_str
            return df_t86

    except Exception as e:
        return None

# ==========================================
# 網頁 UI 與主程式
# ==========================================

st.title("🚀 台股籌碼雙買與爆量掃描器")
st.markdown("自動抓取近 7 個交易日資料，找出外資、投信買超與爆量訊號。")

if st.button("開始掃描 (抓取最新 7 日資料)", type="primary"):
    
    all_data = []
    days_collected = 0
    current_date = datetime.now()
    
    # 安全煞車機制：避免因被鎖 IP 或連假太長導致無限迴圈
    max_attempts = 30  
    attempts = 0       
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    while days_collected < 7 and attempts < max_attempts:
        date_str = current_date.strftime("%Y%m%d")
        
        # 只抓平日 (0=週一 ~ 4=週五)
        if current_date.weekday() < 5: 
            status_text.text(f"👉 正在獲取 {date_str} 的資料... (已收集 {days_collected}/7 天)")
            daily_df = fetch_daily_data(date_str)
            
            if daily_df is not None:
                all_data.append(daily_df)
                days_collected += 1
                progress_bar.progress(days_collected / 7)
                time.sleep(5)  # 成功抓到，休息 5 秒保護連線
            else:
                status_text.warning(f"⚠️ {date_str} 無法取得資料，繼續嘗試前一天...")
                time.sleep(3)  # 失敗也休息 3 秒，避免被鎖 IP
                
        current_date -= timedelta(days=1)
        attempts += 1
        
    if days_collected < 7:
        st.error("❌ 抓取失敗：超過最大嘗試次數！可能是證交所尚未公布資料，或者您的網路 IP 暫時被證交所阻擋，請稍後再試。")
    else:
        status_text.success("✅ 資料收集完畢，開始進行運算！")

    # ==========================================
    # 數據運算與排版顯示
    # ==========================================
    if all_data and days_collected == 7:
        try:
            combined_df = pd.concat(all_data)
            
            # 1. 籌碼加總
            summary_df = combined_df.groupby(['代號', '名稱'])[['外資買賣超', '投信買賣超']].sum().reset_index()
            summary_df['外資買超(張)'] = (summary_df['外資買賣超'] / 1000).astype(int)
            summary_df['投信買超(張)'] = (summary_df['投信買賣超'] / 1000).astype(int)
            
            top20_foreign = summary_df.sort_values(by='外資買超(張)', ascending=False).head(20)
            top20_trust = summary_df.sort_values(by='投信買超(張)', ascending=False).head(20)
            
            # 2. 篩選外資投信雙買
            dual_buy = summary_df[(summary_df['外資買超(張)'] > 0) & (summary_df['投信買超(張)'] > 0)].copy()
            dual_buy['雙買總和(張)'] = dual_buy['外資買超(張)'] + dual_buy['投信買超(張)']
            top20_dual = dual_buy.sort_values(by='雙買總和(張)', ascending=False).head(20)
            
            # 3. 爆量計算
            latest_date = combined_df['日期'].max()
            latest_vol = combined_df[combined_df['日期'] == latest_date].groupby('代號')['成交量'].sum()
            prev_vol_avg = combined_df[combined_df['日期'] != latest_date].groupby('代號')['成交量'].mean()
            
            # 對齊資料並補 0
            latest_vol, prev_vol_avg = latest_vol.align(prev_vol_avg, fill_value=0)
            
            # 爆量條件：今日大於前幾日平均的 1.5 倍，且今日大於 0
            vol_surge_series = (latest_vol > (prev_vol_avg * 1.5)) & (latest_vol > 0)
            surge_codes = vol_surge_series[vol_surge_series].index.tolist()
            
            top20_dual['爆量訊號'] = top20_dual['代號'].apply(lambda x: '🔥 是' if x in surge_codes else '否')

            # 4. 在網頁上顯示精美的表格分頁
            st.divider()
            tab1, tab2, tab3 = st.tabs(["🔥 同步買超 & 爆量", "🟢 外資買超 Top 20", "🔴 投信買超 Top 20"])
            
            with tab1:
                st.subheader("🏆 【外資與投信 同步買超】近 7 個交易日")
                if not top20_dual.empty:
                    st.dataframe(top20_dual[['代號', '名稱', '外資買超(張)', '投信買超(張)', '雙買總和(張)', '爆量訊號']], use_container_width=True, hide_index=True)
                else:
                    st.info("近期無外資與投信同步買超之個股。")
                
            with tab2:
                st.subheader("🏆 【外資】買超前 20 名")
                st.dataframe(top20_foreign[['代號', '名稱', '外資買超(張)']], use_container_width=True, hide_index=True)
                
            with tab3:
                st.subheader("🏆 【投信】買超前 20 名")
                st.dataframe(top20_trust[['代號', '名稱', '投信買超(張)']], use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"運算過程中發生錯誤: {e}")