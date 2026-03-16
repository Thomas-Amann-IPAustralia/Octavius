import docx

def parse_docx_to_hansel_markdown(uploaded_file):
    """
    Parses a DOCX file into a flat text format with semantic markers
    that the Hansel linter expects (e.g., __SEMANTIC_ITALIC_START__).
    """
    doc = docx.Document(uploaded_file)
    full_text = []

    for para in doc.paragraphs:
        para_text = ""

        # Heading detection
        heading_level = 0
        if para.style.name.startswith('Heading'):
            try:
                # Extract level from 'Heading 1', 'Heading 2', etc.
                heading_level = int(para.style.name.split()[-1])
            except (ValueError, IndexError):
                # Fallback for just 'Heading' style
                heading_level = 1

        if heading_level > 0:
            para_text += f"__SEMANTIC_H{heading_level}_START__"

        for run in para.runs:
            run_text = run.text
            if not run_text:
                continue

            # Note: docx run italic/bold can be True, False, or None (inherit)
            if run.italic:
                run_text = f"__SEMANTIC_ITALIC_START__{run_text}__SEMANTIC_ITALIC_END__"
            if run.bold:
                run_text = f"__SEMANTIC_BOLD_START__{run_text}__SEMANTIC_BOLD_END__"

            para_text += run_text

        if heading_level > 0:
            para_text += f"__SEMANTIC_H{heading_level}_END__"

        if para_text.strip():
            full_text.append(para_text)

    return "\n\n".join(full_text)
