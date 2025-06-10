
args=("$@")
echo wget -qO- --post-data ${args[0]} http://192.168.10.223/position/set
wget -qO- --post-data ${args[0]} http://192.168.10.223/position/set
