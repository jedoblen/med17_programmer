# Manual de instalação (Fase 1)

## Requisitos
- Windows 10/11 64 bits
- **Python 3.10+ de 64 bits** (para a interface). Verifique: `py -3-64 --version`
- Para a Fase 2: Python 32 bits adicional (`py -3-32`), apenas para a ponte J2534.
  Ambos podem coexistir.

## Instalação
```bat
cd med17_programmer
py -3-64 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## Executar
```bat
set PYTHONPATH=src
python -m med17
```
PowerShell: `$env:PYTHONPATH="src"; python -m med17`

## Testes
```bat
pytest
```
Os testes da interface usam o modo offscreen do Qt. São testes **simulados**, sem ECU nem interface J2534.

## Onde ficam os dados
`%APPDATA%\MED17Programmer\` — `config.json`, `logs\med17.log` (rotativo), `backups\`.
Para usar outra pasta: variável de ambiente `MED17_HOME`.

## Problemas comuns
- `No module named med17`: faltou `set PYTHONPATH=src`.
- `No matching distribution for PySide6`: você está usando Python 32 bits; use o de 64 bits.
