@echo off

rmdir /s /q "C:\kafka\logs"
rmdir /s /q "C:\kafka\tmp"

start powershell -ExecutionPolicy Bypass -NoExit -File .\lanzarZookeeper.ps1
start powershell -ExecutionPolicy Bypass -NoExit -File .\lanzarKafka.ps1

timeout /t 8 >nul

start powershell -ExecutionPolicy Bypass -NoExit -File .\crearTopics.ps1
