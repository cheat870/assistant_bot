Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "d:\Build_Project_With_Ai\Tools\crack_iclaud\telegram_assistant_bot"
WshShell.Run """d:\Build_Project_With_Ai\Tools\crack_iclaud\.venv\Scripts\pythonw.exe"" main.py", 0, False
