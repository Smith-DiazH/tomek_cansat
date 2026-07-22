import spidev

spi = spidev.SpiDev()
spi.open(1, 0)

spi.max_speed_hz = 500000
spi.mode = 0

tx = [1,2,3,4,5,6,7,8]

rx = spi.xfer2(tx)

print("TX:", tx)
print("RX:", rx)

spi.close()
