#!/usr/bin/env python3
import os
import re
import subprocess
import sys

UPSTREAM_REPO = "https://github.com/kushagrasinghx/BitChord.git"
UPSTREAM_BRANCH = "main"

def run(cmd, check=True, capture=True):
    print(f"+ {' '.join(cmd)}")
    res = subprocess.run(cmd, check=check, capture_output=capture, text=True)
    if capture and res.stdout:
        print(res.stdout.strip())
    return res

def get_extra(filepath, key):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    m = re.search(rf'extra\["{key}"\]\s*=\s*"?([^"\n]+)"?', content)
    return m.group(1).strip() if m else None

def set_extra(filepath, key, val, is_string=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    quote = '"' if is_string else ''
    new_content = re.sub(rf'extra\["{key}"\]\s*=\s*("[^"\n]+"|[^\n]+)', f'extra["{key}"] = {quote}{val}{quote}', content)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

def ensure_apple_id(app_gradle_path):
    with open(app_gradle_path, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = re.sub(r'applicationId\s*=\s*"[^"]+"', 'applicationId = "com.apple.android.music"', content)
    if 'tasks.named("assembleProdRelease")' not in new_content:
        hook = '\ntasks.named("assembleProdRelease") {\n    finalizedBy(rootProject.tasks.named("publishObtainiumRelease"))\n}\n'
        new_content += hook
    with open(app_gradle_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

def main():
    remotes = run(['git', 'remote']).stdout.split()
    target_remote = 'origin' if 'origin' in remotes else 'myfork'
    
    # Ensure upstream remote exists
    if 'upstream' not in remotes:
        run(['git', 'remote', 'add', 'upstream', UPSTREAM_REPO])
    
    run(['git', 'fetch', 'upstream', UPSTREAM_BRANCH])
    
    # Check if upstream has new commits
    rev_list = run(['git', 'rev-list', '--count', f'HEAD..upstream/{UPSTREAM_BRANCH}']).stdout.strip()
    commits_ahead = int(rev_list) if rev_list.isdigit() else 0
    if commits_ahead == 0:
        print("sync: No new commits in upstream. Everything is up to date.")
        sys.exit(0)
    
    print(f"sync: Found {commits_ahead} new upstream commits. Merging...")
    
    current_code = int(get_extra("build.gradle.kts", "bitchordVersionCode") or 44)
    
    try:
        upstream_gradle = run(['git', 'show', f'upstream/{UPSTREAM_BRANCH}:build.gradle.kts']).stdout
        m_code = re.search(r'extra\["bitchordVersionCode"\]\s*=\s*(\d+)', upstream_gradle)
        upstream_code = int(m_code.group(1)) if m_code else 0
        m_name = re.search(r'extra\["bitchordVersionName"\]\s*=\s*"([^"]+)"', upstream_gradle)
        upstream_name = m_name.group(1) if m_name else None
    except Exception as e:
        print(f"sync: warning reading upstream gradle: {e}")
        upstream_code = 0
        upstream_name = None
    
    run(['git', 'config', 'user.name', 'github-actions[bot]'])
    run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'])
    
    merge_res = subprocess.run(['git', 'merge', f'upstream/{UPSTREAM_BRANCH}', '-m', f'chore(sync): merge {commits_ahead} commits from upstream kushagrasinghx/BitChord'], capture_output=True, text=True)
    if merge_res.returncode != 0:
        print(f"sync: Merge conflict encountered. Resolving with custom overrides: {merge_res.stderr}")
        subprocess.run(['git', 'checkout', '--ours', 'build.gradle.kts', 'app/build.gradle.kts'], capture_output=True)
        subprocess.run(['git', 'add', '-A'], capture_output=True)
    
    ensure_apple_id("app/build.gradle.kts")
    
    new_code = max(current_code + 1, upstream_code + 1)
    set_extra("build.gradle.kts", "bitchordVersionCode", new_code, is_string=False)
    if upstream_name:
        set_extra("build.gradle.kts", "bitchordVersionName", upstream_name, is_string=True)
    
    print(f"sync: Updated bitchordVersionCode to {new_code}")
    
    run(['git', 'add', '-A'])
    subprocess.run(['git', 'commit', '-m', f'chore(sync): bump versionCode to {new_code} and enforce com.apple.android.music'], capture_output=True)
    
    run(['git', 'push', target_remote, 'main'])
    print("sync: Successfully pushed synced changes to main branch.")
    
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        print("sync: Triggering Android Release APK workflow via gh CLI...")
        run(['gh', 'workflow', 'run', 'android.yml', '--ref', 'main'])
    else:
        print("sync: GH_TOKEN not available; done.")

if __name__ == "__main__":
    main()
