' Runs the agent with no console window.
' A visible window is a thing that gets closed, and closing it kills the agent.
Set shell = CreateObject("WScript.Shell")
shell.Run "cmd /c ""D:\git\stargazer\run.bat""", 0, False
