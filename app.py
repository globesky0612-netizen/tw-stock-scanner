import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# 1. 網頁基本設定 (可自訂標題與圖示)
st.set_page_config(page_title="台股籌碼爆量掃描器", page_icon="📈", layout="wide")

# 這裡放入你原本寫好的 fetch_daily_data 函式
@st.cache_data(ttl=3600) # 加入快取功能，避免每次切換畫面都重新爬蟲
def fetch_daily_data(date_str):
    # ... (這裡完全貼上你原本的 fetch_daily_data 程式碼，將 print 改成 st.write 或省略) ...
    # 為了版面簡潔，我這裡省略細節，請放入你原本的 try-except 區塊
    pass

# ==========================================
# 網頁 UI 與主程式
# ==========================================

st.title("🚀 台股籌碼雙買與爆量掃描器")
st.markdown("自動抓取近 7 個交易日資料，找出外資、投信買超與爆量訊號。")

# 使用按鈕來觸發掃描，避免一開網頁就狂抓資料
if st.button("開始掃描 (抓取最新 7 日資料)", type="primary"):
    
    all_data = []
    days_collected = 0
    current_date = datetime.now()
    
    # 使用進度條與提示訊息，讓 UI 更順暢
    progress_bar = st.progress(0)
    status_text = st.empty()

    while days_collected < 7:
        date_str = current_date.strftime("%Y%m%d")
        if current_date.weekday() < 5: 
            status_text.text(f"👉 正在獲取 {date_str} 的資料...")
            daily_df = fetch_daily_data(date_str) # 呼叫你的爬蟲函式
            
            if daily_df is not None:
                all_data.append(daily_df)
                days_collected += 1
                progress_bar.progress(days_collected / 7)
                time.sleep(2) # 延遲保護機制
        
        current_date -= timedelta(days=1)
        
    status_text.success("✅ 資料收集完畢，開始進行運算！")

    # ==========================================
    # 數據運算與排版顯示
    # ==========================================
    if all_data:
        try:
            combined_df = pd.concat(all_data)
            
            # 1. 籌碼加總 (你的原本邏輯)
            summary_df = combined_df.groupby(['代號', '名稱'])[['外資買賣超', '投信買賣超']].sum().reset_index()
            summary_df['外資買超(張)'] = (summary_df['外資買賣超'] / 1000).astype(int)
            summary_df['投信買超(張)'] = (summary_df['投信買賣超'] / 1000).astype(int)
            
            top20_foreign = summary_df.sort_values(by='外資買超(張)', ascending=False).head(20)
            top20_trust = summary_df.sort_values(by='投信買超(張)', ascending=False).head(20)
            
            # --- 雙買與爆量運算 (省略細節，貼上你的邏輯) ---
            dual_buy = summary_df[(summary_df['外資買超(張)'] > 0) & (summary_df['投信買超(張)'] > 0)].copy()
            dual_buy['雙買總和(張)'] = dual_buy['外資買超(張)'] + dual_buy['投信買超(張)']
            top20_dual = dual_buy.sort_values(by='雙買總和(張)', ascending=False).head(20)
            
            # (假設這裡完成了爆量運算，並新增了 '爆量50%' 欄位)

            # 2. 在網頁上顯示精美的表格
            st.divider() # 水平分隔線
            
            # 使用 Tabs 分頁讓手機版面不會太長
            tab1, tab2, tab3 = st.tabs(["🔥 同步買超 & 爆量", "🟢 外資 Top 20", "🔴 投信 Top 20"])
            
            with tab1:
                st.subheader("🏆 【外資與投信 同步買超】近 7 個交易日")
                st.dataframe(top20_dual[['代號', '名稱', '外資買超(張)', '投信買超(張)', '雙買總和(張)', '爆量50%']], use_container_width=True)
                
            with tab2:
                st.subheader("🏆 【外資】買超前 20 名")
                st.dataframe(top20_foreign[['代號', '名稱', '外資買超(張)']], use_container_width=True)
                
            with tab3:
                st.subheader("🏆 【投信】買超前 20 名")
                st.dataframe(top20_trust[['代號', '名稱', '投信買超(張)']], use_container_width=True)

        except Exception as e:
            st.error(f"運算過程中發生錯誤: {e}")