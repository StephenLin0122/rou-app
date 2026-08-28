import streamlit as st
import re

st.set_page_config(page_title="NC 碼轉檔器", page_icon="⚙️", layout="wide")

st.title("⚙️ NC 碼轉換器 - 跳模陣列與雙進給處理")
st.markdown("不用登入即可直接上傳 NC / ROU 檔進行雙速切削與跳模轉檔。")

# 側邊欄設定區
st.sidebar.header("🔧 跳模與刀具參數設定")

dir_tool_option = st.sidebar.selectbox("1. 選擇套 pin 鑽頭", ["T01", "無"], index=0)

st.sidebar.markdown("---")
st.sidebar.subheader("2. X 方向跳模參數 (R[aa]M02X[bbb])")
x_step_count = st.sidebar.number_input("X 軸跳模數 (aa)", min_value=1, value=13, step=1)
x_step_distance = st.sidebar.number_input("X 間距 mm (bbb)", min_value=0.0, value=18.2, step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("3. Y 方向跳模參數 (R[aa]M02Y[bbb])")
y_step_count = st.sidebar.number_input("Y 軸跳模數 (aa)", min_value=1, value=8, step=1)
y_step_distance = st.sidebar.number_input("Y 間距 mm (bbb)", min_value=0.0, value=46.2, step=0.1)

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

def process_rou_content(lines, dir_tool_option, x_count, x_dist, y_count, y_dist):
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

    final_header_lines = []
    for line in header_lines:
        if re.match(r"^T\d+C.*", line, re.IGNORECASE):
            t_num_raw = re.match(r"^T(\d+)", line, re.IGNORECASE).group(1)
            t_code_formatted = f"T{int(t_num_raw):02d}"
            
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

    return "".join(new_lines)

uploaded_files = st.file_uploader("📂 選擇並載入 NC / ROU 檔案", accept_multiple_files=True)

if uploaded_files:
    st.success(f"已成功載入 {len(uploaded_files)} 個檔案，設定參數後即可點擊下載：")
    for uploaded_file in uploaded_files:
        content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        lines = content.splitlines(keepends=True)
        
        result_text = process_rou_content(
            lines, 
            dir_tool_option, 
            x_step_count, 
            x_step_distance, 
            y_step_count, 
            y_step_distance
        )
        
        output_filename = "modified_" + uploaded_file.name
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text(f"📄 準備完成：{output_filename}")
        with col2:
            st.download_button(
                label=f"⬇️ 下載轉檔",
                data=result_text,
                file_name=output_filename,
                mime="text/plain",
                key=uploaded_file.name
            )
