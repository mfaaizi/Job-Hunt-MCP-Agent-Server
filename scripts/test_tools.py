"""
Manual test script — call MCP tools directly as plain Python functions,
without needing a full MCP client. Useful for debugging each tool in isolation.

Run: python scripts/test_tools.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.tools.resume_parser import parse_resume, get_parsed_resume, list_resumes


def main():
    resume_path = "data/resumes/Faaiz_resume.pdf"  # adjust filename if different

    print(f"Parsing resume: {resume_path}")
    result = parse_resume(resume_path)
    print(json.dumps(result, indent=2))

    print("\nAll parsed resumes:", list_resumes())

    print("\nFull normalized CV:")
    cv = get_parsed_resume()
    print(json.dumps(cv, indent=2)[:1000], "...")


if __name__ == "__main__":
    main()
