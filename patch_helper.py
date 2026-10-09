with open(r'C:\Users\mimoh\Desktop\schudel maker\extractor.py', 'r', encoding='utf-8', errors='replace') as f:
    s = f.read()

# add helper after render_chars
helper = '''
def _split_cell_stream(page, cell_bbox, text):
    if not cell_bbox or not text:
        return text, '', ''
    x0, top, x1, bottom = cell_bbox
    divs = _find_dividers(page, cell_bbox, tol=5.0, span_ratio=0.3)
    if not divs:
        return text, '', ''
    best = divs[0]
    for d in divs[1:]:
        f = (d['x'] - x0) / (x1 - x0) if (x1 - x0) > 0 else 0
        fb = (best['x'] - x0) / (x1 - x0) if (x1 - x0) > 0 else 0
        if abs(f - 0.5) < abs(fb - 0.5) + 1e-9:
            best = d
    dx = best['x']
    lines = _cell_lines_chars(page, cell_bbox)
    left_lines, right_lines, full_lines = [], [], []
    for ln in lines:
        mid = (ln['top'] + ln['bottom']) / 2
        inside = best['top'] - 2.5 <= mid <= best['bottom'] + 2.5
        if inside:
            L = [c for c in ln['chars'] if (c['x0'] + c['x1']) / 2 < dx]
            R = [c for c in ln['chars'] if (c['x0'] + c['x1']) / 2 >= dx]
            if L:
                left_lines.append(_render_chars(L))
            if R:
                right_lines.append(_render_chars(R))
        else:
            s = _render_chars(ln['chars'])
            if s:
                full_lines.append(s)
    return '\\n'.join(left_lines).strip(), '\\n'.join(right_lines).strip(), '\\n'.join(full_lines).strip()
'''

if '_split_cell_stream' not in s:
    s = s.replace('def _render_chars(chars):\n    return \'\'.join(c[\'text\'] for c in chars).strip()\n\n\n',
                  'def _render_chars(chars):\n    return \'\'.join(c[\'text\'] for c in chars).strip()\n\n' + helper + '\n\n')

with open(r'C:\Users\mimoh\Desktop\schudel maker\extractor.py', 'w', encoding='utf-8') as f:
    f.write(s)
print('ok')
