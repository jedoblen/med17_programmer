# Captura passiva de diagnóstico (descoberta de IDs e protocolo)

Objetivo: descobrir, com o seu scanner funcionando, quais IDs CAN, bitrate e tipo de protocolo a ECU usa.
A captura **não transmite nada**. Não faz parte de leitura/gravação.

## Ligação
1. VCI2 e scanner no mesmo barramento CAN (OBD com derivação em Y, ou ligação de bancada pelos pinos CAN H/CAN L
   conforme a documentação da sua ECU). ECU alimentada de forma estável.
2. Bitrate: comece por 500 kbit/s (o programa usa o valor salvo na aba Conexão). Bitrate errado gera
   quadros de erro e pode derrubar a comunicação do scanner: se isso ocorrer, desconecte e tente outro.
3. Não capture durante gravação/programação.

## Execução
```bat
python tools/can_capture.py --segundos 90
```
Durante a captura, no scanner faça só operações de **leitura**: identificação da ECU, leitura de falhas
e dados em tempo real. Evite codificação, adaptação ou qualquer programação.

Saída: `captura.csv` e um relatório com IDs observados e candidatos a par tester → ECU.
Para reanalisar um CSV: `python tools/can_capture.py --arquivo captura.csv`.

## Privacidade
O CSV pode conter o chassi (VIN) e números de série nos dados. Revise antes de compartilhar.

## Se nada for encontrado
O scanner pode estar usando a linha K (pino 7 do OBD), outro bitrate ou outro formato de endereçamento.
Este software só implementa CAN: se o diagnóstico da ECU for pela linha K, será preciso outro caminho.
