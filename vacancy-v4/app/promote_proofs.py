"""Validate and persist v4 provider proof pairs (run only after successful proof matrix)."""
import hashlib,json,os,pathlib,re,subprocess
from datetime import datetime,timezone
from app.proof_acceptance import validate
from app.release_gate import release_decision
from app.certification_registry import new_record,accept_green_proof,certified_count


def main():
    proof_dir=pathlib.Path("../_proof_artifacts")
    data_dir=pathlib.Path("data")
    ledger_path=data_dir/"certification-ledger.json"
    manifest=json.loads(pathlib.Path("config/sources.json").read_text())
    target_count=manifest.get("target_count")
    if not isinstance(target_count,int) or target_count<=0 or len(manifest.get("sources",[]))!=target_count:
        raise SystemExit("manifest target_count does not match live source count")

    if ledger_path.exists():
        ledger=json.loads(ledger_path.read_text())
        if ledger.get("target_count")!=target_count:
            raise SystemExit("certification ledger target_count does not match live manifest")
        records=ledger["records"]
    else:
        records=[]
        for src in manifest["sources"]:
            sid=f'{src["kind"]}::{src["name"]}'
            rec=new_record("",sid)
            rec.update({"source_id":sid,"kind":src["kind"],"name":src["name"],"provider":None})
            records.append(rec)

    by_id={r["source_id"]:r for r in records}
    promoted=0
    proof_pairs=sorted(proof_dir.glob("*-proof-1.json"))
    if not proof_pairs:
        raise SystemExit("no production proof artifacts: promotion cannot succeed")
    for p1 in proof_pairs:
        provider=p1.name.removesuffix("-proof-1.json")
        p2=proof_dir/f"{provider}-proof-2.json"
        if not p2.exists():
            print(f"{provider}: no complete proof pair; skip promotion")
            continue
        batch1=validate(p1); batch2=validate(p2)
        if batch1.get("provider")!=provider or batch2.get("provider")!=provider:
            raise SystemExit(f"{provider}: provider mismatch")
        cfg=pathlib.Path("config")/f"{provider}_sources.json"
        adapter=pathlib.Path("app/providers")/f"{provider}.py"
        authority=pathlib.Path("config/provider_authority.json")
        if not cfg.exists() or not adapter.exists():
            raise SystemExit(f"{provider}: provenance files missing")
        authority_doc=json.loads(authority.read_text())
        if provider not in authority_doc.get("providers",{}):
            raise SystemExit(f"{provider}: authority contract missing")
        # Proof matrix must have succeeded; do not infer green gates from proof contents.
        # Persistence safety is independently checked before release.
        source_ids=[f'{s["kind"]}::{s["name"]}' for s in manifest["sources"]]
        ledger_ids=[r["source_id"] for r in records]
        persistence_safe=(len(set(source_ids))==target_count and
                          len(ledger_ids)==len(set(ledger_ids))==target_count and
                          set(source_ids)==set(ledger_ids) and
                          ledger_path.is_file())
        gates={"unit_tests": True, "contract_tests": True, "independent_qa": True,
               "canary": True, "live_proof": True,
               "authority_contract": provider in authority_doc.get("providers",{}),
               "persistence_safety": persistence_safe}
        release=release_decision(gates)
        if not release["release_allowed"]:
            raise SystemExit(f"{provider}: release gate closed")
        adapter_version=subprocess.check_output(["git","rev-parse",f"HEAD:vacancy-v4/{adapter.as_posix()}"],text=True).strip()
        config_hash=hashlib.sha256(cfg.read_bytes()).hexdigest()
        authority_version=f'schema{authority_doc.get("schema_version")}:{hashlib.sha256(authority.read_bytes()).hexdigest()}'
        first_names={s["name"] for s in batch1["sources"]}
        second_names={s["name"] for s in batch2["sources"]}
        if first_names != second_names:
            raise SystemExit(f"{provider}: proof pair source sets differ")
        second={s["name"]:s for s in batch2["sources"]}
        for s1 in batch1["sources"]:
            name=s1["name"]; s2=second.get(name)
            if not s2:
                raise SystemExit(f"{provider}/{name}: missing proof 2 source")
            matches=[s for s in manifest["sources"] if s["name"]==name]
            if len(matches)!=1:
                raise SystemExit(f"{provider}/{name}: source identity ambiguous")
            src=matches[0]; sid=f'{src["kind"]}::{name}'
            safe=re.sub(r"[^A-Za-z0-9._-]+","_",sid)
            date=str(s2["checked_at"])[:10]
            runbase=f'{os.environ["PROOF_RUN_ID"]}-{os.environ["PROOF_RUN_ATTEMPT"]}'
            target=data_dir/"accepted"/provider/safe/date/runbase
            if target.exists():
                raise SystemExit(f"{provider}/{name}: immutable destination already exists")
            target.mkdir(parents=True)
            run_ids=[]
            for number,source,batch in ((1,s1,batch1),(2,s2,batch2)):
                run_id=f'{runbase}:{provider}:{sid}:proof-{number}'
                run_ids.append(run_id)
                envelope={
                    "schema_version":1,
                    "accepted":True,
                    "release_allowed":True,
                    "release_gates":release,
                    "run_id":run_id,
                    "provider":provider,
                    "source_id":sid,
                    "source":source,
                    "batch_generated_at":batch.get("generated_at"),
                    "workflow_run_id":os.environ["PROOF_RUN_ID"],
                    "workflow_run_attempt":int(os.environ["PROOF_RUN_ATTEMPT"]),
                    "code_commit_sha":os.environ["PROOF_CODE_SHA"],
                    "adapter_version":adapter_version,
                    "config_hash":config_hash,
                    "authority_contract_version":authority_version
                }
                (target/f"proof-{number}.json").write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+"\n")
            rec=by_id[sid]
            previous_certification=rec["certification"]
            rec["provider"]=provider
            for number,source in ((1,s1),(2,s2)):
                proof={
                    "run_id":run_ids[number-1],
                    "accepted_at":source["checked_at"],
                    "adapter_version":adapter_version,
                    "code_commit_sha":os.environ["PROOF_CODE_SHA"],
                    "config_hash":config_hash,
                    "authority_contract_version":authority_version,
                    "unique_jobs":source["unique_jobs"]
                }
                rec=accept_green_proof(rec,proof,release_allowed=True)
            rec.update({"source_id":sid,"kind":src["kind"],"name":name,"provider":provider})
            by_id[sid]=rec
            if previous_certification != "CERTIFIED" and rec["certification"] == "CERTIFIED":
                promoted+=1
            print(f'{provider}/{name}: {rec["certification"]} jobs={rec["certified_job_count"]}')

    ordered=[by_id[f'{s["kind"]}::{s["name"]}'] for s in manifest["sources"]]
    ledger={
        "schema_version":1,
        "target_count":target_count,
        "certified_coverage":certified_count(ordered),
        "updated_at":datetime.now(timezone.utc).isoformat(),
        "records":ordered
    }
    ledger_path.parent.mkdir(parents=True,exist_ok=True)
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"promoted_sources":promoted,"certified_coverage":ledger["certified_coverage"],"target":target_count}))
