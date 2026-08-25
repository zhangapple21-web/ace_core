import json

from autonomous_audit import run_audit


def main():
    result = run_audit()
    print(json.dumps({"overall_state": result["report"]["overall_state"], "written": sorted(result["written"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
