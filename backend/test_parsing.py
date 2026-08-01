import sys
from app.parsing import extract_questions_from_xlsx

if len(sys.argv) < 2:
    print("Usage: python3 test_parsing.py <path_to_xlsx>")
    sys.exit(1)

file_path = sys.argv[1]

results = extract_questions_from_xlsx(file_path)
print(f"Extracted {len(results)} rows\n")

for r in results:
    print(r.row_number, "|", r.question_text)

suspects = [r for r in results if "?" not in r.question_text and len(r.question_text) < 40]
print(f"\n{len(suspects)} suspect rows (no '?', short text):")
for r in suspects:
    print(r.row_number, "|", repr(r.question_text))