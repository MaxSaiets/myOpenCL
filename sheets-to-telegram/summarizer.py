def summarize_sheet_data(values):
    """
    Summarize the sheet data.
    For now, we return a simple summary: number of rows and columns, and the first row as header.
    """
    if not values:
        return "No data found in the sheet."

    num_rows = len(values)
    num_cols = len(values[0]) if values else 0

    summary = f"Sheet Summary:\n"
    summary += f"- Rows: {num_rows}\n"
    summary += f"- Columns: {num_cols}\n"

    if num_rows > 0:
        header = values[0]
        summary += f"- Header: {', '.join(header)}\n"

    # If there are more rows, show a sample of the first few data rows
    if num_rows > 1:
        summary += f"- First data row: {', '.join(values[1])}\n"
    if num_rows > 2:
        summary += f"- Second data row: {', '.join(values[2])}\n"

    return summary