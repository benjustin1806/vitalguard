import os
import sys
from dulwich import porcelain
from dulwich.repo import Repo

def push_repo(token=None):
    repo_path = '.'
    remote_url = "https://github.com/benjustin1806/vitalguard.git"
    
    # 1. Stage all untracked & modified files
    files = ["README.md", ".gitignore", "requirements.txt", "backend/main.py", "backend/hospitals.json", "backend/patients.json", "backend/staff.json", "backend/test_ws.py", "frontend/index.html", "frontend/patients.html", "frontend/patient.html", "frontend/login.html", "cv/iv_monitor.py", "ml/train.py", "ml/feature_columns.json", "phase6-plan.md", "phase7-plan.md"]

    print("Staging project files...")
    for f in files:
        if os.path.exists(f):
            porcelain.add(repo_path, [f])
            
    # 2. Commit if there are changes
    try:
        commit_id = porcelain.commit(
            repo_path,
            message="feat: VitalGuard release version update",
            author="Ben Justin <benjustin1806@github.com>",
            committer="Ben Justin <benjustin1806@github.com>"
        )
        print(f"Committed SHA: {commit_id.decode('utf-8')[:8]}")
    except Exception as e:
        print(f"Commit status: {e}")

    # 3. Push to remote
    auth_url = f"https://{token}@github.com/benjustin1806/vitalguard.git" if token else remote_url

    print("Pushing to GitHub repository...")
    try:
        porcelain.push(repo_path, auth_url, refspecs=b'refs/heads/main:refs/heads/main')
        print("\n✅ Successfully pushed to https://github.com/benjustin1806/vitalguard.git !")
    except Exception as e:
        print(f"\nPush result: {e}")
        if not token:
            print("\nGitHub requires authentication. Run:")
            print("   .\\.venv\\Scripts\\python.exe push.py YOUR_GITHUB_PERSONAL_ACCESS_TOKEN")


if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else None
    push_repo(token)
