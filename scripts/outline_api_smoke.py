import os
import sys
from pathlib import Path


database = Path("/tmp/ledger-outline-smoke.db")
database.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{database}"
os.environ["STORAGE_DIR"] = "/tmp/ledger-outline-uploads"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient

from app.main import app


with TestClient(app) as client:
    curriculum = client.get("/api/curriculum").json()
    subject_id = curriculum[0]["subjects"][0]["id"]
    content = "# 收入准则\n\n## 合同识别\n\n合同识别应当根据资料所列条件判断。\n\n## 履约义务\n\n履约义务需要单独识别。"
    response = client.post(
        "/api/documents",
        data={"subject_id": str(subject_id)},
        files={"file": ("收入讲义.md", content.encode(), "text/markdown")},
    )
    response.raise_for_status()
    document = response.json()
    proposal = client.get(f"/api/documents/{document['id']}/outline").json()
    assert proposal["status"] == "review"
    assert len(proposal["nodes"]) == 1
    assert len(proposal["nodes"][0]["children"]) == 2
    confirm = client.post(f"/api/outline-proposals/{proposal['id']}/confirm")
    confirm.raise_for_status()
    assert confirm.json()["created_chapters"] == 1
    second = client.post(f"/api/outline-proposals/{proposal['id']}/confirm").json()
    assert second["idempotent"] is True
    names = [chapter["name"] for chapter in client.get("/api/curriculum").json()[0]["subjects"][0]["chapters"]]
    assert "收入准则" in names
    print("outline API smoke passed")
