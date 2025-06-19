cd C:\kafka

.\bin\windows\kafka-topics.bat --create --topic posicion --bootstrap-server localhost:9092 --partitions 20
.\bin\windows\kafka-topics.bat --create --topic movimiento --bootstrap-server localhost:9092 --partitions 20
.\bin\windows\kafka-topics.bat --create --topic recorrido --bootstrap-server localhost:9092 --partitions 20
.\bin\windows\kafka-topics.bat --create --topic mapa --bootstrap-server localhost:9092 --partitions 20
.\bin\windows\kafka-topics.bat --create --topic destino --bootstrap-server localhost:9092 --partitions 20
