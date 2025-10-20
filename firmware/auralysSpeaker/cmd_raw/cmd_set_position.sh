
args=("$@")
echo wget -qO- --post-data ${args[0]} http://192.168.10.34/position/set
wget -qO- --post-data ${args[0]} http://192.168.10.34/position/set
