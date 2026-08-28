import streamlit as st
import re

st.set_page_config(page_title="NC 碼轉換器", page_icon="⚒️", layout="centered")

st.subheader("⚒️ 【NC 碼轉換器 - 跳模陣列與雙進給處理】")
st.markdown("##### **請設定共用跳模陣列參數 (R[aa]M02X/Y[bbb])：**")

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

enable_delete_tool = st.checkbox("🗑️ 開啟刪除刀具功能")
delete_tool_code = ""
if enable_delete_tool:
    delete_tool_code = st.text_input("請輸入要刪除的刀號 (例如: T03)", value="T03").strip().upper()

st.markdown("---")

uploaded_files = st.file_uploader("📂 1. 選擇並載入 NC 檔案", accept_multiple_files=True)

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

if uploaded_files:
    for uploaded_file in uploaded_files:
        content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        lines = content.splitlines(keepends=True)
        
        header_lines = []
        tool_blocks = []
        header_tools = {} # 紀錄標頭定義的刀號與原始字串/C值
        
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
                # 正確匹配 C 後面可能帶有的負號
                match_header_t = re.search(r"^(T\d+)C(-?\d+(\.\d+)?)", line_str, re.IGNORECASE)
                if match_header_t:
                    t_id = f"T{int(re.sub(r'^\D+', '', match_header_t.group(1))):02d}"
                    c_val = float(match_header_t.group(2))
                    is_rout_header = ("(R)" in line_str.upper()) or (c_val < 0)
                    header_tools[t_id] = {
                        "c_val": c_val,
                        "raw_line": line_str,
                        "is_rout": is_rout_header
                    }
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

        # 剔除要刪除的刀具
        if enable_delete_tool and delete_tool_code:
            tool_blocks = [tb for tb in tool_blocks if f"T{int(re.sub(r'^\D+', '', tb[0])):02d}" != delete_tool_code]

        # 綜合標頭與內文 (是否有 G 碼) 來判斷是否為 Routing 刀
        analyzed_tools = {}
        for t_code, body in tool_blocks:
            t_std = f"T{int(re.sub(r'^\D+', '', t_code)):02d}"
            
            # 檢查內文中是否有 G01/G02/G03/G00 命令
            has_g_code = any(re.search(r"G0?[0-3]", line, re.IGNORECASE) for line in body)
            
            header_info = header_tools.get(t_std, {"c_val": 1.0, "is_rout": False})
            is_rout = header_info["is_rout"] or has_g_code
            
            analyzed_tools[t_std] = {
                "body": body,
                "c_val": header_info["c_val"],
                "is_rout": is_rout
            }

        drill_tools = [t for t, info in analyzed_tools.items() if not info["is_rout"]]
        rout_tools = [t for t, info in analyzed_tools.items() if info["is_rout"]]

        st.success(f"✅ 成功載入檔案：{uploaded_file.name}")
        st.info(f"🔍 自動識別結果：鑽孔刀 {len(drill_tools)} 支，Routing 刀 {len(rout_tools)} 支")

        dir_tool_option = st.selectbox(f"🎯 選擇套 pin 鑽頭 ({uploaded_file.name})", ["T01", "無"], index=0)

        st.markdown("---")
        
        st.markdown("**[鑽孔刀具 - 將自動進行同尺寸合併]**")
        for t_code in drill_tools:
            c_val = analyzed_tools[t_code]["c_val"]
            st.checkbox(f"{t_code} (C{abs(c_val):.1f}) → 套用鑽孔跳模", value=True, key=f"d_{t_code}_{uploaded_file.name}")

        st.markdown("\n**[Routing 刀具 - 維持獨立刀號與 M25 跳模/雙進給]**")
        for t_code in rout_tools:
            c_val = analyzed_tools[t_code]["c_val"]
            st.checkbox(f"{t_code} (C-{abs(c_val):.1f}) → 套用 Routing M25 雙進給跳模", value=True, key=f"r_{t_code}_{uploaded_file.name}")

        st.markdown("---")

        x_dist_str = format_distance(x_step_distance)
        y_dist_str = format_distance(y_step_distance)
        
        step_repeat_block = [
            "M01\n",
            f"R{x_step_count}M02X{x_dist_str}\n",
            "M01\n",
            f"R{y_step_count}M02Y{y_dist_str}\n"
        ]

        final_header_lines = []
        for line in header_lines:
            match_t = re.search(r"^(T\d+)C(-?\d+(\.\d+)?)", line, re.IGNORECASE)
            if match_t:
                t_num_raw = re.match(r"^T(\d+)", line, re.IGNORECASE).group(1)
                t_code_formatted = f"T{int(t_num_raw):02d}"
                
                if enable_delete_tool and delete_tool_code and t_code_formatted == delete_tool_code:
                    continue

                tool_info = analyzed_tools.get(t_code_formatted)
                if tool_info and tool_info["is_rout"]:
                    val_str = f"{abs(tool_info['c_val']):.1f}"
                    final_header_lines.append(f"{t_code_formatted}C-{val_str}(R)")
                else:
                    final_header_lines.append(line)
            else:
                final_header_lines.append(line)

        new_lines = [line + "\n" for line in final_header_lines]
        new_lines.append("%\n")

        output_blocks = []
        has_t01 = ("T01" in analyzed_tools)

        if not has_t01 and dir_tool_option == "T01":
            t01_coords_list = ["X0Y0", "X01Y0", "X29Y0", "X29Y391", "X0Y391"]
            output_blocks.append({
                "t_code": "T01",
                "body": t01_coords_list,
                "is_rout": False
            })

        for t_code, info in analyzed_tools.items():
            cleaned_body = clean_block_lines(info["body"])
            output_blocks.append({
                "t_code": t_code,
                "body": cleaned_body,
                "is_rout": info["is_rout"]
            })

        total_len = len(output_blocks)
        for idx, blk in enumerate(output_blocks):
            t_code = blk["t_code"]
            body = blk["body"]
            is_rout = blk["is_rout"]

            is_next = (idx + 1 < total_len)
            end_code = "M47" if is_next else "M30"

            if is_rout:
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
                new_lines.extend(step_repeat_block)
                new_lines.append("M08\n")
                new_lines.append(f"{end_code}\n\n")

        result_text = "".join(new_lines)
        output_filename = "modified_" + uploaded_file.name

        st.download_button(
            label=f"⬇️ 下載轉檔檔案 ({output_filename})",
            data=result_text,
            file_name=output_filename,
            mime="text/plain",
            key=f"dl_{uploaded_file.name}"
        )
