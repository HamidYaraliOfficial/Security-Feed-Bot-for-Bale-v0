Security Feed Bot for Bale  (ربات رصد امنیتی برای بله)
=======================================================

FAST START
  Windows     : double-click  start_windows.bat
  Linux / Mac : ./start_linux_mac.sh
  Then your browser opens the control panel (http://127.0.0.1:8765). Fill the fields, press "Test", then "Start".

Full step-by-step guide (Persian):  GUIDE_fa.pdf

Server mode (no panel, uses data/config.json):   python run.py --headless
Change panel port:                                python run.py --port 9000

Files
  run.py            entry point
  app/              source code (bale client, feed fetcher, sqlite store, worker, local panel)
  data/config.json  your settings (contains the bot token - do not share it!)
  data/bot.db       small queue + dedup database (posts are deleted right after they are sent)
