import streamlit as st
import re

st.set_page_config(page_title="NC 碼轉換器", page_icon="⚒️", layout="centered")

# 標頭設定
st.subheader("⚒️ 【NC 碼轉換器 - 跳模陣列與雙進給處理】")
st.markdown("##### **請設定共用跳模陣列參數 (R[aa]M02X/Y[bbb])：**")

# 主頁面參數輸入框 (依原版預設值設定)
col_x1, col_x2 = st.columns(2)
with col_x1:
    x_step_count = st.number_input("X 軸跳模數(aa)", min_value=1, value=17, step=1)
with col_x2:
    x_step_distance = st.number_input("X 間距mm(bbb)", min_value=0.0, value=1.4, step=0.1, format="%.1f")

col_y1, col_y2 = st.columns(2)
with col_y1:
    y_step_count = st.number_input("Y 軸跳模數(aa)", min_value=1, value=8, step=1)
with col_y2:
    y_step_distance = st.number_input("Y 間距mm(bbb)", min_value=0.0, value=47.6, step=0.1, format="%.1f")

st.markdown("---")

# 刪除刀具功能選項
enable_delete_tool = st.checkbox("🗑️ 開啟刪除刀具功能")
delete_tool_code = ""
if enable_delete_tool:
    delete_tool_code = st.text_input("請輸入要刪除的刀號 (例如: T03)", value="T03").strip().upper()

st.markdown("---")

# 橘色客製風格按鈕 UI
st.markdown("""
    <style>
    div[data-testid="stFileUploader"] {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

uploaded_files = st.file_uploader("📂 1. 選擇並載入 NC 檔案", accept_multiple_files=True)

# 輔助函式定義
def format_distance(val):
    val_int = int(round(val * 10))
    if val_int < 10:
        return f"{val_int:02d}"
    elif val_int < 100:
        return f"{val_int:03d}"
    else:
        return f"{val_int:04d}"

def clean_block_lines(lines_list):
    cleaned = []
    for l in lines_list:
        line_str = l.strip()
        if not line_str:
            continue
        if line_str in ["M08", "M47", "M30", "M01", "M25"] or line_str.startswith("R") or "M02" in line_str:
            continue
        cleaned.append(line_str)
    return cleaned

def format_tool_header(line, t_num):
    match = re.search(r"C-?(\d+(\.\d+)?)", line, re.IGNORECASE)
    if match:
        full_val_str = match.group(1)
        if "." in full_val_str:
            int_p, dec_p = full_val_str.split(".")
            tool_val = f"{int(int_p)}.{dec_p}"
        else:
            tool_val = f"{int(full_val_str)}.0"
    else:
        tool_val = f"{int(t_num)}.0"
    return f"T{t_num}C-{tool_val}(R)"

def process_rou_content(lines, dir_tool_option, x_count, x_dist, y_count, y_dist, delete_t_code):
    x_dist_str = format_distance(x_dist)
    y_dist_str = format_distance(y_dist)
    
    step_repeat_block = [
        "M01\n",
        f"R{x_count}M02X{x_dist_str}\n",
        "M01\n",
        f"R{y_count}M02Y{y_dist_str}\n"
    ]

    header_lines = []
    tool_blocks = []
    current_t_code = None
    current_body = []
    in_header = True

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        if line_str == "%":
            in_header = False
            continue

        if in_header:
            header_lines.append(line_str)
        else:
            match_t = re.match(r'^(T\d+)\s*$', line_str, re.IGNORECASE)
            if match_t:
                if current_t_code is not None:
                    tool_blocks.append((current_t_code, current_body))
                current_t_code = match_t.group(1).upper()
                current_body = []
            else:
                if current_t_code is not None:
                    current_body.append(line_str)

    if current_t_code is not None:
        tool_blocks.append((current_t_code, current_body))

    # 刪除指定的刀具區塊
    if delete_t_code:
        tool_blocks = [tb for tb in tool_blocks if f"T{int(re.sub(r'^\D+', '', tb[0])):02d}" != delete_t_code]

    final_header_lines = []
    for line in header_lines:
        if re.match(r"^T\d+C.*", line, re.IGNORECASE):
            t_num_raw = re.match(r"^T(\d+)", line, re.IGNORECASE).group(1)
            t_code_formatted = f"T{int(t_num_raw):02d}"
            
            # 若為刪除刀具，則不寫入標頭
            if delete_t_code and t_code_formatted == delete_t_code:
                continue

            is_rout = False
            for t_code, body in tool_blocks:
                t_block_num = f"T{int(re.sub(r'^\D+', '', t_code)):02d}"
                if t_block_num == t_code_formatted:
                    is_rout = True
                    break
            
            if is_rout:
                final_header_lines.append(format_tool_header(line, f"{int(t_num_raw):02d}"))
            else:
                final_header_lines.append(line)
        else:
            final_header_lines.append(line)

    new_lines = [line + "\n" for line in final_header_lines]
    new_lines.append("%\n")

    output_blocks = []
    has_t01 = any(f"T{int(re.sub(r'^\D+', '', t_code)):02d}" == "T01" for t_code, _ in tool_blocks)

    if not has_t01 and dir_tool_option == "T01":
        t01_coords_list = ["X0Y0", "X01Y0", "X29Y0", "X29Y391", "X0Y391"]
        output_blocks.append({
            "t_code": "T01",
            "body": t01_coords_list,
            "do_step": True
        })

    for t_code, body_lines in tool_blocks:
        t_num = re.sub(r'^\D+', '', t_code)
        t_code_std = f"T{int(t_num):02d}"
        cleaned_body = clean_block_lines(body_lines)
        output_blocks.append({
            "t_code": t_code_std,
            "body": cleaned_body,
            "do_step": True
        })

    total_len = len(output_blocks)
    
    for idx, blk in enumerate(output_blocks):
        t_code = blk["t_code"]
        body = blk["body"]
        do_step = blk["do_step"]

        is_next_step = (idx + 1 < total_len) and output_blocks[idx + 1]["do_step"]
        end_code = "M47" if (do_step and is_next_step) else "M30"

        if do_step:
            new_lines.append(f"{t_code}\n")
            new_lines.append("F006\n")
            new_lines.append("M25\n")
            if body: new_lines.append("\n".join(body) + "\n")
            new_lines.extend(step_repeat_block)
            new_lines.append("M08\n")
            new_lines.append("\nF016\n")
            new_lines.append("M25\n")
            if body: new_lines.append("\n".join(body) + "\n")
            new_lines.extend(step_repeat_block)
            new_lines.append("M08\n")
            new_lines.append(f"{end_code}\n\n")
        else:
            new_lines.append(f"{t_code}\n")
            if body: new_lines.append("\n".join(body) + "\n")
            new_lines.append("M30\n\n")

    drill_count = 1 if (not has_t01 and dir_tool_option == "T01") else 0
    rout_count = len(output_blocks) - drill_count

    return "".join(new_lines), drill_count, rout_count

# 處理檔案上傳與轉換邏輯
if uploaded_files:
    for uploaded_file in uploaded_files:
        content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        lines = content.splitlines(keepends=True)
        
        # 下拉選單選擇套 pin 鑽頭
        dir_tool_option = st.selectbox(f"🎯 選擇套 pin 鑽頭 ({uploaded_file.name})", ["T01", "無"], index=0)

        result_text, drill_cnt, rout_cnt = process_rou_content(
            lines, 
            dir_tool_option, 
            x_step_count, 
            x_step_distance, 
            y_step_count, 
            y_step_distance,
            delete_tool_code if enable_delete_tool else ""
        )
        
        st.success(f"✅ 成功載入檔案：{uploaded_file.name}")
        st.info(f"🔍 自動識別結果：鑽孔刀 {drill_cnt} 支，Routing 刀 {rout_cnt} 支")
        
        output_filename = "modified_" + uploaded_file.name
        st.download_button(
            label=f"⬇️ 下載轉檔檔案 ({output_filename})",
            data=result_text,
            file_name=output_filename,
            mime="text/plain"
        )
