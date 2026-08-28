import ipywidgets as widgets
from IPython.display import display, clear_output
from google.colab import output
import re
import os

style = {'description_width': 'initial'}
main_output = widgets.Output()

def format_distance_lz(val):
    val_int = int(round(val * 10))
    return f"{val_int:03d}" if val_int < 100 else f"{val_int:04d}"

# ==========================================
# NC 檔案解析邏輯 (自動判別 Drill 與 Routing)
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

    for t_code, b_lines in raw_sections.items():
        has_m15 = any('M15' in l.upper() for l in b_lines)
        has_m17 = any('M17' in l.upper() for l in b_lines)
        tool_types[t_code] = (has_m15 and has_m17)

    return header_lines, detected_tools, tool_sizes, raw_sections, tool_types


# 全域檔案傳輸暫存與處理 Handle
current_file_handler = None

def js_upload_callback(filename, content):
    global current_file_handler
    if current_file_handler:
        current_file_handler(filename, content)

output.register_callback('notebook.direct_upload', js_upload_callback)

# 生成直覺選檔按鈕 (橘色系)
def make_direct_upload_btn(btn_text="📂 1. 選擇並載入 NC 檔案", bg_color="#f57c00"):
    btn_id = "btn_" + str(hash(btn_text) & 0xffffffff)
    html_code = f"""
    <div style="margin: 8px 0;">
      <label for="{btn_id}" style="
        background-color: {bg_color};
        color: white;
        padding: 10px;
        font-size: 14px;
        border-radius: 4px;
        cursor: pointer;
        display: inline-block;
        width: 320px;
        text-align: center;
        font-weight: 500;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        transition: background-color 0.3s;
      ">
        {btn_text}
      </label>
      <input type="file" id="{btn_id}" style="display:none;" onchange="uploadDirect_{btn_id}(this)">
    </div>

    <script>
    function uploadDirect_{btn_id}(input) {{
      const file = input.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(e) {{
        google.colab.kernel.invokeFunction('notebook.direct_upload', [file.name, e.target.result], {{}});
      }};
      reader.readAsText(file);
    }}
    </script>
    """
    return widgets.HTML(value=html_code)


# ==========================================
# 主 UI 畫面
# ==========================================
def render_ui():
    global current_file_handler
    with main_output:
        clear_output()
        print("🛠️ 【NC 碼轉換器 - 跳模陣列與雙進給處理】")
        x_count = widgets.IntText(value=17, description='X 軸跳模數(aa):', style=style)
        x_dist = widgets.FloatText(value=1.4, description='X 間距mm(bbb):', style=style)
        y_count = widgets.IntText(value=8, description='Y 軸跳模數(aa):', style=style)
        y_dist = widgets.FloatText(value=47.6, description='Y 間距mm(bbb):', style=style)
        enable_delete = widgets.Checkbox(value=False, description='🗑️ 開啟刪除刀具功能', style=style)

        upload_html_btn = make_direct_upload_btn("📂 1. 選擇並載入 NC 檔案", bg_color="#f57c00")
        process_out = widgets.Output()

        display(widgets.VBox([
            widgets.HTML("<b>請設定共用跳模陣列參數 (R[aa]M02X/Y[bbb])：</b>"),
            x_count, x_dist, y_count, y_dist,
            widgets.HTML("<br>"), enable_delete,
            widgets.HTML("<br>"), upload_html_btn, process_out
        ]))

        def handle_upload(filename, content):
            with process_out:
                clear_output()
                header_lines, raw_detected_tools, raw_tool_sizes, raw_sections, tool_types = parse_raw_mixed_file(content)
                output_filename = f"processed_{filename}"

                drill_tools = [t for t in raw_detected_tools if not tool_types[t]]
                routing_tools = [t for t in raw_detected_tools if tool_types[t]]

                print(f"✅ 成功載入檔案: {filename}")
                print(f"🔍 自動識別結果：鑽孔刀 {len(drill_tools)} 支，Routing 刀 {len(routing_tools)} 支\n")

                pin_drill_dropdown = widgets.Dropdown(
                    options=[('無 (不加 M30)', None)] + [(t, t) for t in drill_tools],
                    value=None,
                    description='🎯 選擇套pin鑽頭:',
                    style=style
                )

                checkboxes = {}
                delete_checkboxes = {}
                row_widgets = [pin_drill_dropdown, widgets.HTML("<hr>")]

                if drill_tools:
                    row_widgets.append(widgets.HTML("<b>[鑽孔刀具 - 將自動進行同尺寸合併]</b>"))
                    for t_code in drill_tools:
                        has_g85 = any('G85' in l.upper() for l in raw_sections.get(t_code, []))
                        tag_str = " (Slot/G85)" if has_g85 else ""
                        cb_step = widgets.Checkbox(value=True, description=f"{t_code} (C{raw_tool_sizes[t_code]}){tag_str} → 套用鑽孔跳模", style=style)
                        checkboxes[t_code] = cb_step

                        cb_del = widgets.Checkbox(value=False, description="🗑️ 刪除此刀具", style=style)
                        delete_checkboxes[t_code] = cb_del
                        row_widgets.append(widgets.HBox([cb_step, cb_del]))

                if routing_tools:
                    row_widgets.append(widgets.HTML("<br><b>[Routing 刀具 - 維持獨立刀號與 M25 跳模/雙進給]</b>"))
                    for t_code in routing_tools:
                        has_g85 = any('G85' in l.upper() for l in raw_sections.get(t_code, []))
                        tag_str = " (Slot/G85)" if has_g85 else ""
                        cb_step = widgets.Checkbox(value=True, description=f"{t_code} (C-{raw_tool_sizes[t_code]}){tag_str} → 套用 Routing M25 雙進給跳模", style=style)
                        checkboxes[t_code] = cb_step

                        cb_del = widgets.Checkbox(value=False, description="🗑️ 刪除此刀具", style=style)
                        delete_checkboxes[t_code] = cb_del
                        row_widgets.append(widgets.HBox([cb_step, cb_del]))

                # 📌 連動邏輯：選為套 Pin 鑽頭時，自動取消跳模並停用/隱藏該勾選項
                def on_pin_change(change):
                    selected_pin = pin_drill_dropdown.value
                    for t_code in drill_tools:
                        cb = checkboxes[t_code]
                        if t_code == selected_pin:
                            cb.value = False
                            cb.disabled = True
                            cb.description = f"{t_code} (C{raw_tool_sizes[t_code]}) → 🎯 已設為套 Pin 鑽頭 (一律不跳模)"
                        else:
                            cb.disabled = False
                            has_g85 = any('G85' in l.upper() for l in raw_sections.get(t_code, []))
                            tag_str = " (Slot/G85)" if has_g85 else ""
                            cb.description = f"{t_code} (C{raw_tool_sizes[t_code]}){tag_str} → 套用鑽孔跳模"

                pin_drill_dropdown.observe(on_pin_change, names='value')

                def update_del_vis(change_del):
                    for cb_del in delete_checkboxes.values():
                        cb_del.layout.display = 'inline-flex' if enable_delete.value else 'none'

                enable_delete.observe(update_del_vis, names='value')

                btn_gen = widgets.Button(description="🚀 確定輸出 NC 碼", button_style='success', layout=widgets.Layout(width='280px', height='40px'))
                display(widgets.VBox(row_widgets + [widgets.HTML("<br>"), btn_gen]))
                update_del_vis(None)

                def run_transform(b_gen):
                    valid_drill_tools = [
                        t for t in drill_tools
                        if not (enable_delete.value and delete_checkboxes.get(t) and delete_checkboxes[t].value)
                    ]
                    valid_routing_tools = [
                        t for t in routing_tools
                        if not (enable_delete.value and delete_checkboxes.get(t) and delete_checkboxes[t].value)
                    ]

                    aa_x_val, bbb_x_val = x_count.value, format_distance_lz(x_dist.value)
                    aa_y_val, bbb_y_val = y_count.value, format_distance_lz(y_dist.value)
                    selected_pin_tool = pin_drill_dropdown.value

                    size_to_primary_drill = {}
                    merged_drill_order = []
                    merged_drill_sizes = {}
                    merged_drill_blocks = {}
                    merged_drill_is_slot = {}

                    for old_t in valid_drill_tools:
                        sz = raw_tool_sizes[old_t]
                        # 📌 雙重防呆：只要是套 Pin 鑽頭，強制 is_step = False (不跳模)
                        is_step = False if old_t == selected_pin_tool else checkboxes[old_t].value
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
                        is_step = checkboxes[old_t].value
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

                    with open(output_filename, 'w', encoding='utf-8') as f: f.writelines(new_lines)
                    print(f"\n✅ NC 檔轉換成功！檔名：【{output_filename}】")
                    from google.colab import files
                    files.download(output_filename)

                btn_gen.on_click(run_transform)

        current_file_handler = handle_upload

display(main_output)
render_ui()
