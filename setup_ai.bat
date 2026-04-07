@echo off
echo ======================================
echo AI CONTEXT ENGINE SETUP BASLIYOR
echo ======================================

cd /d D:\PROJECT\LOJINEXTv2

echo [1/6] Python kontrol...
python --version
IF %ERRORLEVEL% NEQ 0 (
    echo Python yok! Lutfen Python kur.
    pause
    exit
)

echo [2/6] Virtual environment olusturuluyor...
python -m venv .ai_env

call .ai_env\Scripts\activate

echo [3/6] Paketler kuruluyor...
pip install --upgrade pip

pip install tree_sitter
pip install networkx
pip install tiktoken
pip install rich
pip install watchdog

echo [4/6] AI klasor yapisi olusturuluyor...
mkdir .ai 2>nul
mkdir .ai\cache 2>nul
mkdir .ai\context 2>nul
mkdir .ai\memory 2>nul
mkdir .ai\agents 2>nul

echo [5/6] Config dosyalari yaziliyor...

echo {> .ai\config.json
echo   "compression_level": "high",>> .ai\config.json
echo   "max_tokens": 20000,>> .ai\config.json
echo   "ignore_dirs": ["node_modules","dist",".git",".ai_env"],>> .ai\config.json
echo   "file_types": [".py",".js",".ts",".md",".json"]>> .ai\config.json
echo }>> .ai\config.json

echo # AGENT TANIMI > .ai\agents\main_agent.md
echo Projeyi analiz et, sadece gerekli dosyalari sec ve optimize et.>> .ai\agents\main_agent.md

echo [6/6] Basit context engine yaziliyor...

echo import os> .ai\engine.py
echo import json>> .ai\engine.py
echo from pathlib import Path>> .ai\engine.py

echo config = json.load(open(".ai/config.json"))>> .ai\engine.py
echo ignore = config["ignore_dirs"]>> .ai\engine.py

echo def scan():>> .ai\engine.py
echo ^    files = []>> .ai\engine.py
echo ^    for root, dirs, filenames in os.walk("."):>> .ai\engine.py
echo ^        if any(x in root for x in ignore): continue>> .ai\engine.py
echo ^        for f in filenames:>> .ai\engine.py
echo ^            if any(f.endswith(ext) for ext in config["file_types"]):>> .ai\engine.py
echo ^                files.append(os.path.join(root, f))>> .ai\engine.py
echo ^    return files>> .ai\engine.py

echo def build_context():>> .ai\engine.py
echo ^    files = scan()[:20]>> .ai\engine.py
echo ^    context = "">> .ai\engine.py
echo ^    for f in files:>> .ai\engine.py
echo ^        try:>> .ai\engine.py
echo ^            with open(f,"r",encoding="utf-8") as file:>> .ai\engine.py
echo ^                content = file.read()[:2000]>> .ai\engine.py
echo ^                context += f"\\n### {f}\\n{content}\\n">> .ai\engine.py
echo ^        except: pass>> .ai\engine.py
echo ^    return context>> .ai\engine.py

echo if __name__ == "__main__":>> .ai\engine.py
echo ^    ctx = build_context()>> .ai\engine.py
echo ^    open(".ai/context/output.txt","w",encoding="utf-8").write(ctx)>> .ai\engine.py
echo ^    print("Context hazir!")>> .ai\engine.py

echo ======================================
echo KURULUM TAMAMLANDI
echo ======================================
pause