# Notes de réseaux

## Poignée de main TCP

TCP établit une connexion en trois étapes, appelée poignée de main en trois temps
(three-way handshake). Le client envoie un segment SYN, le serveur répond par un segment
SYN-ACK, puis le client confirme avec un segment ACK. Une fois ces trois segments échangés,
les données peuvent circuler dans les deux sens.

## TCP et UDP

TCP est orienté connexion : il garantit la livraison des données, leur ordre et le contrôle
de flux. UDP n'établit pas de connexion et ne garantit ni la livraison ni l'ordre ; il est
plus léger et convient au streaming ou aux requêtes DNS.

## Masque de sous-réseau

Le masque de sous-réseau indique quels bits d'une adresse IP identifient le réseau et quels
bits identifient la machine. Avec un masque /24, les 24 premiers bits désignent le réseau et
il reste 8 bits pour les machines, soit 254 adresses utilisables, car l'adresse du réseau et
l'adresse de diffusion sont réservées.

## DNS

Le DNS traduit un nom de domaine en adresse IP.
