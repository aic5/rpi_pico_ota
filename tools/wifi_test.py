import network, time

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wlan.connect("SteAle2", "edce7b36b6")

for i in range(40):
    st = wlan.status()
    print(i, "status:", st, "connected:", wlan.isconnected())
    if wlan.isconnected() or st < 0:
        break
    time.sleep(0.5)

print("final status:", wlan.status())
print("ifconfig:", wlan.ifconfig())
