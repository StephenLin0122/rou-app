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
        raw_tool_blocks = []
        header_c_vals = {}
        header_has_r_tag = {}
        
        current_t = None
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
                # 相容 C1.、C1.0、C-1.0 等寫法
                match_t = re.search(r"T(\d+)C(-?\d+(?:\.\d*)?)", line_str, re.IGNORECASE)
                if match_t:
                    t_num = f"T{int(match_t.group(1)):02d}"
                    c_val = float(match_t.group(2))
                    header_c_vals[t_num] = abs(c_val)
                    header_has_r_tag[t_num] = ("(R)" in line_str.upper()) or (c_val < 0)
            else:
                match_t = re.match(r'^T(\d+)', line_str, re.IGNORECASE)
                if match_t:
                    if current_t is not None:
                        raw_tool_blocks.append((current_t, current_body))
                    current_t = f"T{int(match_t.group(1)):02d}"
                    current_body = []
                else:
                    if current_t is not None:
                        current_body.append(line_str)

        if current_t is not None:
            raw_tool_blocks.append((current_t, current_body))

        if enable_delete_tool and delete_tool_code:
            raw_tool_blocks = [tb for tb in raw_tool_blocks if tb[0] != delete_tool_code]

        analyzed_tools = {}
        drill_list = []
        rout_list = []

        for t_code, body in raw_tool_blocks:
            # 修正關鍵：嚴格匹配 G00~G03 或 G0~G3，且後面不能直接接數字 (避免誤抓 G05)
            has_g_code = any(re.search(r'G(00|01|02|03|0|1|2|3)(?!\d)', l, re.IGNORECASE) for l in body)
            
            is_rout = header_has_r_tag.get(t_code, False) or has_g_code
            c_val = header_c_vals.get(t_code, 1.0)

            analyzed_tools[t_code] = {
                "body": body,
                "c_val": c_val,
                "is_rout": is_rout
            }

            if is_rout:
                rout_list.append(t_code)
            else:
                drill_list.append(t_code)

        st.success(f"✅ 成功載入檔案：{uploaded_file.name}")
        st.info(f"🔍 自動識別結果：鑽孔刀 {len(drill_list)} 支，Routing 刀 {len(rout_list)} 支")

        dir_tool_option = st.selectbox(f"🎯 選擇套 pin 鑽頭 ({uploaded_file.name})", ["T01", "無"], index=0)

        st.markdown("---")
        st.markdown("**[鑽孔刀具 - 將自動進行同尺寸合併]**")
        for t_code in drill_list:
            c_v = analyzed_tools[t_code]["c_val"]
            st.checkbox(f"{t_code} (C{c_v:.1f}) → 套用鑽孔跳模", value=True, key=f"d_{t_code}_{uploaded_file.name}")

        st.markdown("\n**[Routing 刀具 - 維持獨立刀號與 M25 跳模/雙進給]**")
        for t_code in rout_list:
            c_v = analyzed_tools[t_code]["c_val"]
            st.checkbox(f"{t_code} (C-{c_v:.1f}) → 套用 Routing M25 雙進給跳模", value=True, key=f"r_{t_code}_{uploaded_file.name}")

        st.markdown("---")

        x_dist_str = format_distance(x_step_distance)
        y_dist_str = format_distance(y_step_distance)
        
        step_repeat_block = [
            "M01\n",
            f"R{x_step_count}M02X{x_dist_str}\n",
            "M01\n",
            f"R{y_step_count}M02Y{y_dist_str}\n"
        ]

        final_header = []
        for line in header_lines:
            match_t = re.search(r"T(\d+)C(-?\d+(?:\.\d*)?)", line, re.IGNORECASE)
            if match_t:
                t_code = f"T{int(match_t.group(1)):02d}"
                if enable_delete_tool and delete_tool_code and t_code == delete_tool_code:
                    continue
                
                info = analyzed_tools.get(t_code)
                if info:
                    if info["is_rout"]:
                        final_header.append(f"{t_code}C-{info['c_val']:.1f}(R)")
                    else:
                        final_header.append(f"{t_code}C{info['c_val']:.1f}")
                else:
                    final_header.append(line)
            else:
                final_header.append(line)

        new_lines = [l + "\n" for l in final_header]
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
