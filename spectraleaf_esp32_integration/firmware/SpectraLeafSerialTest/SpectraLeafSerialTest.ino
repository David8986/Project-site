/*
  SpectraLeaf serial hardware test

  Use this first to test:
  - servo/filter movement on GPIO13
  - light transistor control on GPIO14

  Open Serial Monitor at 115200 baud and send commands:

    help
    status
    light on
    light off
    light toggle
    move 532
    move 556
    move 680
    move 725
    move 850
    move 940
    angle 90

  Wiring:
    Servo signal -> GPIO13
    Light transistor base/gate control -> GPIO14
    Common GND between ESP32, servo supply and light supply

  Do not power the servo from the ESP32 3.3V pin.
*/

#include <Arduino.h>
#include <ESP32Servo.h>

static const int SERVO_PIN = 13;
static const int LIGHT_PIN = 14;
static const bool LIGHT_ACTIVE_HIGH = true;

static const int SERVO_MIN_US = 500;
static const int SERVO_MAX_US = 2500;

struct BandPosition {
  int wavelength;
  int angle;
};

BandPosition BANDS[] = {
  {532, 0},
  {556, 30},
  {680, 60},
  {725, 90},
  {850, 120},
  {940, 150},
};
static const int BAND_COUNT = sizeof(BANDS) / sizeof(BANDS[0]);

Servo filterServo;
String inputLine = "";
int currentAngle = 0;
int currentBand = 532;
bool lightOn = false;

void setLight(bool enabled) {
  lightOn = enabled;
  bool outputHigh = LIGHT_ACTIVE_HIGH ? enabled : !enabled;
  digitalWrite(LIGHT_PIN, outputHigh ? HIGH : LOW);
}

void moveServoToAngle(int angle) {
  currentAngle = constrain(angle, 0, 180);
  filterServo.write(currentAngle);
  Serial.print("OK servo angle ");
  Serial.println(currentAngle);
}

bool moveToBand(int wavelength) {
  for (int i = 0; i < BAND_COUNT; i++) {
    if (BANDS[i].wavelength == wavelength) {
      currentBand = wavelength;
      moveServoToAngle(BANDS[i].angle);
      Serial.print("OK band ");
      Serial.print(wavelength);
      Serial.print(" angle ");
      Serial.println(BANDS[i].angle);
      return true;
    }
  }
  Serial.print("ERR unknown band ");
  Serial.println(wavelength);
  return false;
}

void printHelp() {
  Serial.println();
  Serial.println("SpectraLeaf serial test commands:");
  Serial.println("  help");
  Serial.println("  status");
  Serial.println("  light on");
  Serial.println("  light off");
  Serial.println("  light toggle");
  Serial.println("  move 532 | 556 | 680 | 725 | 850 | 940");
  Serial.println("  angle 0..180");
  Serial.println();
}

void printStatus() {
  Serial.println("STATUS");
  Serial.print("  servo_pin: ");
  Serial.println(SERVO_PIN);
  Serial.print("  light_pin: ");
  Serial.println(LIGHT_PIN);
  Serial.print("  current_band: ");
  Serial.println(currentBand);
  Serial.print("  current_angle: ");
  Serial.println(currentAngle);
  Serial.print("  light: ");
  Serial.println(lightOn ? "on" : "off");
}

String lowerTrimmed(String text) {
  text.trim();
  text.toLowerCase();
  return text;
}

void handleCommand(String command) {
  command = lowerTrimmed(command);
  if (command.length() == 0) return;

  if (command == "help" || command == "?") {
    printHelp();
    return;
  }

  if (command == "status") {
    printStatus();
    return;
  }

  if (command == "light on") {
    setLight(true);
    Serial.println("OK light on");
    return;
  }

  if (command == "light off") {
    setLight(false);
    Serial.println("OK light off");
    return;
  }

  if (command == "light toggle") {
    setLight(!lightOn);
    Serial.print("OK light ");
    Serial.println(lightOn ? "on" : "off");
    return;
  }

  if (command.startsWith("move ")) {
    int wavelength = command.substring(5).toInt();
    moveToBand(wavelength);
    return;
  }

  if (command.startsWith("angle ")) {
    int angle = command.substring(6).toInt();
    moveServoToAngle(angle);
    return;
  }

  Serial.print("ERR unknown command: ");
  Serial.println(command);
  Serial.println("Send 'help' for commands.");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(LIGHT_PIN, OUTPUT);
  setLight(false);

  filterServo.setPeriodHertz(50);
  filterServo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
  moveServoToAngle(BANDS[0].angle);

  Serial.println();
  Serial.println("SpectraLeaf serial hardware test ready.");
  printHelp();
}

void loop() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (inputLine.length() > 0) {
        handleCommand(inputLine);
        inputLine = "";
      }
    } else {
      inputLine += ch;
    }
  }
}
