import streamlit as st
import re

st.set_page_config(page_title="NC 碼轉換器", page_icon="⚒️", layout="centered")

st.subheader("⚒️ 【NC 碼轉換器 - 跳模陣列與雙進給處理】")
st.markdown("##### **請設定共用跳模陣列參數 (R[aa]M02X/Y[bbb])：**")

# 1. 介面參數設定
col_x1, col_x2 = st.columns(2)
with col_x1:
    x_count_val = st.number_input("X 軸跳模數(aa):", min_value=1, value=17, step=1)
with col_x2:
    x_dist_val = st.number_input("X 間距mm(bbb):", min_value=0.0, value=1.4, step=0.1, format="%.1f")

col_y1, col_y2 = st.columns(2)
with col_y1:
    y_count_val = st.number_input("Y 軸跳模數(aa):", min_value=1, value=8, step=1)
with col_y2:
    y_dist_val = st.number_input("Y 間距mm(bbb):", min_value=0.0, value=47.6, step=0.1, format="%.1f")

st.markdown("---")

enable_delete = st.checkbox("🗑️ 開啟刪除刀具功能")

st.markdown("---")

uploaded_files = st.file_uploader("📂 1. 選擇並載入 NC 檔案", accept_multiple_files=True)

# 格式化間距函式 (同 Colab 邏輯)
def format_distance_lz(val):
    val_int = int(round(val * 10))
    return f"{val_int:03d}" if val_int < 100 else f"{val_int:04d}"

# ==========================================
# 原版 Colab NC 解析邏輯 (完全對齊)
# ==========================================
def parse_raw_mixed_file(content):
    lines = content.splitlines()
    header_lines, body_lines = [], []
    in_header = True
    tool_sizes = {}
    detected_tools = []

    for line in lines:
        stripped = line.strip()
        if stripped == "%":
            in_header = False
            header_lines.append(line)
            continue
        if in_header:
            header_lines.append(line)
            m_size = re.match(r'^(T\d+)\s*C-?([0-9]*\.?[0-9]*)', stripped, re.IGNORECASE)
            if m_size:
                t_code = m_size.group(1).upper()
                raw_val = m_size.group(2)
                if raw_val.endswith('.'): raw_val += '0'
                if raw_val.startswith('.'): raw_val = '0' + raw_val
                if '.' not in raw_val: raw_val += '.0'
                tool_sizes[t_code] = raw_val
                if t_code not in detected_tools: detected_tools.append(t_code)
        else:
            body_lines.append(line)
            m_tool = re.match(r'^(T\d+)\s*$', stripped, re.IGNORECASE)
            if m_tool:
                t_code = m_tool.group(1).upper()
                if t_code not in detected_tools and t_code != 'T':
                    detected_tools.append(t_code)

    for t in detected_tools:
        if t not in tool_sizes: tool_sizes[t] = "1.0"
    detected_tools.sort(key=lambda x: int(re.search(r'\d+', x).group()))

    raw_sections = {}
    tool_types = {}
    current_t_code = None
    current_body = []

    for l in body_lines:
        line_str = l.strip()
        match_t = re.match(r'^(T\d+)\s*$', line_str, re.IGNORECASE)
        if match_t:
            if current_t_code is not None:
                raw_sections[current_t_code] = current_body
            current_t_code = match_t.group(1).upper()
            current_body = []
        elif current_t_code is not None:
            if line_str in ['M30', 'M08', 'M47']:
                raw_sections[current_t_code] = current_body
                current_t_code = None
            else:
                if line_str.upper() != 'M25':
                    current_body.append(line_str)
    if current_t_code is not None:
        raw_sections[current_t_code] = current_body

    # 原版關鍵判斷：同時有 M15 與 M17 才是 Routing 刀
    for t_code, b_lines in raw_sections.items():
        has_m15 = any('M15' in l.upper() for l in b_lines)
        has_m17 = any('M17' in l.upper() for l in b_lines)
        tool_types[t_code] = (has_m15 and has_m17)

    return header_lines, detected_tools, tool_sizes, raw_sections, tool_types


if uploaded_files:
    for uploaded_file in uploaded_files:
        content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        header_lines, raw_detected_tools, raw_tool_sizes, raw_sections, tool_types = parse_raw_mixed_file(content)

        drill_tools = [t for t in raw_detected_tools if not tool_types.get(t, False)]
        routing_tools = [t for t in raw_detected_tools if tool_types.get(t, False)]

        st.success(f"✅ 成功載入檔案: {uploaded_file.name}")
        st.info(f"🔍 自動識別結果：鑽孔刀 {len(drill_tools)} 支，Routing 刀 {len(routing_tools)} 支")

        # 🎯 選擇套 Pin 鑽頭選項
        pin_options = ["無 (不加 M30)"] + drill_tools
        selected_pin_str = st.selectbox(
            f"🎯 選擇套pin鑽頭 ({uploaded_file.name}):",
            options=pin_options,
            index=0
        )
        selected_pin_tool = None if selected_pin_str.startswith("無") else selected_pin_str

        st.markdown("---")

        checkboxes = {}
        delete_checkboxes = {}

        # 顯示鑽孔刀具勾選區
        if drill_tools:
            st.markdown("**[鑽孔刀具 - 將自動進行同尺寸合併]**")
            for t_code in drill_tools:
                has_g85 = any('G85' in l.upper() for l in raw_sections.get(t_code, []))
                tag_str = " (Slot/G85)" if has_g85 else ""
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    if t_code == selected_pin_tool:
                        st.checkbox(
                            f"{t_code} (C{raw_tool_sizes[t_code]}) → 🎯 已設為套 Pin 鑽頭 (一律不跳模)",
                            value=False, disabled=True, key=f"d_cb_{t_code}_{uploaded_file.name}"
                        )
                        checkboxes[t_code] = False
                    else:
                        checkboxes[t_code] = st.checkbox(
                            f"{t_code} (C{raw_tool_sizes[t_code]}){tag_str} → 套用鑽孔跳模",
                            value=True, key=f"d_cb_{t_code}_{uploaded_file.name}"
                        )
                with col2:
                    if enable_delete:
                        delete_checkboxes[t_code] = st.checkbox("🗑️ 刪除此刀具", value=False, key=f"d_del_{t_code}_{uploaded_file.name}")
                    else:
                        delete_checkboxes[t_code] = False

        # 顯示 Routing 刀具勾選區
        if routing_tools:
            st.markdown("\n**[Routing 刀具 - 維持獨立刀號與 M25 跳模/雙進給]**")
            for t_code in routing_tools:
                has_g85 = any('G85' in l.upper() for l in raw_sections.get(t_code, []))
                tag_str = " (Slot/G85)" if has_g85 else ""
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    checkboxes[t_code] = st.checkbox(
                        f"{t_code} (C-{raw_tool_sizes[t_code]}){tag_str} → 套用 Routing M25 雙進給跳模",
                        value=True, key=f"r_cb_{t_code}_{uploaded_file.name}"
                    )
                with col2:
                    if enable_delete:
                        delete_checkboxes[t_code] = st.checkbox("🗑️ 刪除此刀具", value=False, key=f"r_del_{t_code}_{uploaded_file.name}")
                    else:
                        delete_checkboxes[t_code] = False

        st.markdown("---")

        # 執行轉換並準備下載
        if st.button("🚀 確定輸出 NC 碼", key=f"btn_gen_{uploaded_file.name}"):
            valid_drill_tools = [
                t for t in drill_tools
                if not (enable_delete and delete_checkboxes.get(t, False))
            ]
            valid_routing_tools = [
                t for t in routing_tools
                if not (enable_delete and delete_checkboxes.get(t, False))
            ]

            aa_x_val = x_count_val
            bbb_x_val = format_distance_lz(x_dist_val)
            aa_y_val = y_count_val
            bbb_y_val = format_distance_lz(y_dist_val)

            size_to_primary_drill = {}
            merged_drill_order = []
            merged_drill_sizes = {}
            merged_drill_blocks = {}
            merged_drill_is_slot = {}

            # 同尺寸鑽孔刀合併處理
            for old_t in valid_drill_tools:
                sz = raw_tool_sizes[old_t]
                is_step = False if old_t == selected_pin_tool else checkboxes[old_t]
                raw_lines = [l.strip() for l in raw_sections.get(old_t, []) if l.strip()]
                has_g85 = any('G85' in l.upper() for l in raw_lines)

                if sz not in size_to_primary_drill:
                    size_to_primary_drill[sz] = old_t
                    merged_drill_order.append(old_t)
                    merged_drill_sizes[old_t] = sz
                    merged_drill_blocks[old_t] = []
                    merged_drill_is_slot[old_t] = has_g85
                else:
                    if has_g85:
                        merged_drill_is_slot[size_to_primary_drill[sz]] = True

                primary_t = size_to_primary_drill[sz]
                if raw_lines:
                    merged_drill_blocks[primary_t].append({'lines': raw_lines, 'is_step': is_step})

            final_tool_headers = []
            final_execution_plan = []
            current_t_idx = 1

            for old_t in merged_drill_order:
                new_t = f"T{current_t_idx:02d}"
                sz = merged_drill_sizes[old_t]
                is_slot = merged_drill_is_slot[old_t]
                final_tool_headers.append((new_t, f"C{sz}", is_slot, False))

                has_pin = False
                for sub_old_t in valid_drill_tools:
                    if size_to_primary_drill[raw_tool_sizes[sub_old_t]] == old_t:
                        if sub_old_t == selected_pin_tool:
                            has_pin = True

                final_execution_plan.append({
                    'new_t': new_t, 'type': 'drill', 'blocks': merged_drill_blocks[old_t], 'is_pin_drill': has_pin
                })
                current_t_idx += 1

            for old_t in valid_routing_tools:
                new_t = f"T{current_t_idx:02d}"
                sz = raw_tool_sizes[old_t]
                raw_lines = [l.strip() for l in raw_sections.get(old_t, []) if l.strip()]
                is_step = checkboxes[old_t]
                has_g85 = any('G85' in l.upper() for l in raw_lines)
                final_tool_headers.append((new_t, f"C-{sz}(R)", has_g85, True))
                final_execution_plan.append({
                    'new_t': new_t, 'type': 'routing', 'lines': raw_lines, 'is_step': is_step
                })
                current_t_idx += 1

            new_lines = ["M48\n"]
            for new_t, sz_str, is_slot, _ in final_tool_headers:
                slot_suffix = "(s)" if is_slot else ""
                new_lines.append(f"{new_t}{sz_str}{slot_suffix}\n")
            new_lines.append("%\n")

            total_plan_items = len(final_execution_plan)
            for idx, plan in enumerate(final_execution_plan):
                new_t = plan['new_t']
                p_type = plan['type']
                is_last_item = (idx + 1 == total_plan_items)

                new_lines.append(f"{new_t}\n")

                if p_type == 'drill':
                    blocks = plan['blocks']
                    is_pin_drill = plan['is_pin_drill']

                    for b_idx, blk in enumerate(blocks):
                        lines, is_step = blk['lines'], blk['is_step']
                        if b_idx > 0: new_lines.append("\n")

                        if not is_step:
                            for l in lines: new_lines.append(l + "\n")
                        else:
                            new_lines.append("M25\n")
                            pattern_coords = lines[:-1] if len(lines) > 1 else lines
                            check_hole_coord = lines[-1] if len(lines) > 1 else None

                            for l in pattern_coords: new_lines.append(l + "\n")
                            new_lines.append("M01\n")
                            new_lines.append(f"R{aa_x_val}M02X{bbb_x_val}\n")
                            new_lines.append("M01\n")
                            new_lines.append(f"R{aa_y_val}M02Y{bbb_y_val}\n")
                            new_lines.append("M08\n")
                            if check_hole_coord: new_lines.append(check_hole_coord + "\n")

                    if is_pin_drill:
                        new_lines.append("M30\n\n")
                    else:
                        new_lines.append("\n")

                elif p_type == 'routing':
                    raw_lines, is_step = plan['lines'], plan['is_step']
                    if not is_step:
                        for l in raw_lines: new_lines.append(l + "\n")
                    else:
                        new_lines.append("F006\nM25\n")
                        for l in raw_lines: new_lines.append(l + "\n")
                        new_lines.append(f"M01\nR{aa_x_val}M02X{bbb_x_val}\nM01\nR{aa_y_val}M02Y{bbb_y_val}\nM08\n\n\n")

                        new_lines.append("F016\nM25\n")
                        for l in raw_lines: new_lines.append(l + "\n")
                        new_lines.append(f"M01\nR{aa_x_val}M02X{bbb_x_val}\nM01\nR{aa_y_val}M02Y{bbb_y_val}\n")

                        if not is_last_item:
                            new_lines.append("M08\n\n\nM47\n\n\n")
                        else:
                            new_lines.append("\n\n\nM30\n")

            result_text = "".join(new_lines)
            output_filename = f"processed_{uploaded_file.name}"

            st.download_button(
                label=f"⬇️ 下載轉檔檔案 ({output_filename})",
                data=result_text,
                file_name=output_filename,
                mime="text/plain",
                key=f"dl_btn_{uploaded_file.name}"
            )
