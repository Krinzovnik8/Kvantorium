import serial
import time

def init_ser():
    global ser
    ser = serial.Serial('COM11', 9600, timeout=2) 
    time.sleep(2)

def sens(channel, pin):
    global ser
    message = f"g{channel},{pin}\n"  
    print(f"{message.strip()}") 
    ser.write(message.encode('utf-8'))
    time.sleep(5)
    while True:
        time.sleep(1) 
        response = ser.readline().decode('utf-8').strip() # Считываем строку и декодируем.
        print(f"Я получил {response}")
        try:
            response = int(response)
            break
        except ValueError:
            if "ERROR: Timeout, no response from slave" in response:
                response=float('nan')
                break
            continue
        
    return response

def act(channel,pin,set):
    global ser
    message = f"s{channel},{pin},{set}\n"  
    print(f"{message.strip()}") 
    ser.write(message.encode('utf-8')) 
    response = ser.readline().decode('utf-8').strip() # Считываем строку и декодируем.
    return response