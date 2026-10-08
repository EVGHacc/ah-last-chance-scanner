"""Generate an auditable cached Vacancy v4 report; never send email."""
import argparse
import json
from pathlib import Path
from .gatekeeper_report import audit_classification
from .gatekeeper_matches import build_report


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    for name in ("combined","manifest","provider-map","ledger","output"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--feedback")
    parser.add_argument("--receipts")
    parser.add_argument("--live-checks")
    args = parser.parse_args()
    audit = audit_classification(read(args.manifest),read(args.provider_map),read(args.ledger))
    result = build_report(read(args.combined),audit,
                          feedback=read(args.feedback) if args.feedback else None,
                          receipts=read(args.receipts) if args.receipts else None,
                          live_checks=read(args.live_checks) if args.live_checks else None)
    output = Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"classified":audit["evidence_complete"],"certified":audit["certified"],
                      "matches":result["match_count"],"degraded":result["degraded"]}))


if __name__ == "__main__":
    main()
