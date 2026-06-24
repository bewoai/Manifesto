def copy_row(ws, source_row: int, target_row: int):
    from copy import copy
    for col in range(1, ws.max_column + 1):
        sc = ws.cell(row=source_row, column=col)
        tc = ws.cell(row=target_row, column=col)
        tc.value = sc.value
        if sc.has_style:
            tc.font = copy(sc.font)
            tc.border = copy(sc.border)
            tc.fill = copy(sc.fill)
            tc.number_format = copy(sc.number_format)
            tc.protection = copy(sc.protection)
            tc.alignment = copy(sc.alignment)
