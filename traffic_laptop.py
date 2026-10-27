import cv2
import time
from ultralytics import YOLO


# ==========================================================
# SETTINGS
# ==========================================================

MIN_GREEN_TIME = 5
MAX_GREEN_TIME = 15
YELLOW_TIME = 3

CONFIDENCE = 0.40


# ==========================================================
# LOAD YOLO
# ==========================================================

model = YOLO("yolov8n.pt")


# Vehicles that YOLO should detect
VEHICLES = [
    "car",
    "motorcycle",
    "bus",
    "truck"
]


# ==========================================================
# SIGNAL VARIABLES
# ==========================================================

current_green = "A"

signal_state = "GREEN"

state_start_time = time.time()


WINDOW_TITLE = "AI Adaptive Traffic Signal - Laptop Prototype"

# ==========================================================
# CAMERA
# ==========================================================

print("[INFO] Opening camera...")
camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("[ERROR] Camera not detected. Please ensure your webcam is connected and accessible.")
    exit()

print("[INFO] Camera initialized successfully.")
print("[INFO] Creating display window...")
cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_TITLE, 960, 720)
print("[INFO] Running traffic signal demo.")
print("[INFO] Press 'q' inside the video window or close it to exit.")



# ==========================================================
# DRAW TRAFFIC LIGHT
# ==========================================================

def draw_signal(
        frame,
        x,
        y,
        signal
):

    # Signal box
    cv2.rectangle(
        frame,
        (x - 30, y - 20),
        (x + 30, y + 140),
        (60, 60, 60),
        -1
    )


    red_color = (50, 50, 50)
    yellow_color = (50, 50, 50)
    green_color = (50, 50, 50)


    if signal == "RED":

        red_color = (
            0,
            0,
            255
        )


    elif signal == "YELLOW":

        yellow_color = (
            0,
            255,
            255
        )


    elif signal == "GREEN":

        green_color = (
            0,
            255,
            0
        )


    # RED
    cv2.circle(
        frame,
        (x, y + 10),
        18,
        red_color,
        -1
    )


    # YELLOW
    cv2.circle(
        frame,
        (x, y + 60),
        18,
        yellow_color,
        -1
    )


    # GREEN
    cv2.circle(
        frame,
        (x, y + 110),
        18,
        green_color,
        -1
    )


# ==========================================================
# MAIN LOOP
# ==========================================================

while True:

    success, frame = camera.read()

    if not success:

        print("Camera frame unavailable")

        break


    frame = cv2.flip(
        frame,
        1
    )


    height, width = frame.shape[:2]


    # ------------------------------------------------------
    # Road separation
    # ------------------------------------------------------

    middle = width // 2


    cv2.line(
        frame,
        (middle, 0),
        (middle, height),
        (255, 255, 255),
        3
    )


    # ------------------------------------------------------
    # YOLO detection
    # ------------------------------------------------------

    results = model(
        frame,
        verbose=False
    )


    road_a_count = 0

    road_b_count = 0


    for result in results:

        for box in result.boxes:


            class_id = int(
                box.cls[0]
            )


            name = model.names[
                class_id
            ]


            confidence = float(
                box.conf[0]
            )


            if (
                name not in VEHICLES
                or
                confidence < CONFIDENCE
            ):

                continue


            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0]
            )


            center_x = int(
                (x1 + x2) / 2
            )


            # ------------------------------------------------
            # ROAD A
            # ------------------------------------------------

            if center_x < middle:

                road_a_count += 1

                road_name = "ROAD A"


            # ------------------------------------------------
            # ROAD B
            # ------------------------------------------------

            else:

                road_b_count += 1

                road_name = "ROAD B"


            # Draw bounding box

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (255, 0, 255),
                2
            )


            text = (
                name
                +
                " "
                +
                str(
                    round(
                        confidence,
                        2
                    )
                )
            )


            cv2.putText(
                frame,
                text,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2
            )


            cv2.putText(
                frame,
                road_name,
                (x1, y2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                2
            )


    # ======================================================
    # AI SIGNAL DECISION
    # ======================================================

    elapsed = (
        time.time()
        -
        state_start_time
    )


    # ------------------------------------------------------
    # GREEN STATE
    # ------------------------------------------------------

    if signal_state == "GREEN":


        # Road A currently GREEN
        if current_green == "A":

            # Switch if:
            # Road A empty
            # Road B has vehicles
            # Minimum green completed

            if (
                road_a_count == 0
                and
                road_b_count > 0
                and
                elapsed >= MIN_GREEN_TIME
            ):

                signal_state = "YELLOW"

                state_start_time = time.time()


            # Maximum green protection
            elif (
                elapsed >= MAX_GREEN_TIME
                and
                road_b_count > 0
            ):

                signal_state = "YELLOW"

                state_start_time = time.time()


        # Road B currently GREEN
        elif current_green == "B":

            if (
                road_b_count == 0
                and
                road_a_count > 0
                and
                elapsed >= MIN_GREEN_TIME
            ):

                signal_state = "YELLOW"

                state_start_time = time.time()


            elif (
                elapsed >= MAX_GREEN_TIME
                and
                road_a_count > 0
            ):

                signal_state = "YELLOW"

                state_start_time = time.time()


    # ------------------------------------------------------
    # YELLOW STATE
    # ------------------------------------------------------

    elif signal_state == "YELLOW":

        if elapsed >= YELLOW_TIME:


            if current_green == "A":

                current_green = "B"


            else:

                current_green = "A"


            signal_state = "GREEN"

            state_start_time = time.time()


    # ======================================================
    # DETERMINE SIGNAL COLORS
    # ======================================================

    if current_green == "A":


        if signal_state == "GREEN":

            road_a_signal = "GREEN"


        else:

            road_a_signal = "YELLOW"


        road_b_signal = "RED"


    else:


        road_a_signal = "RED"


        if signal_state == "GREEN":

            road_b_signal = "GREEN"


        else:

            road_b_signal = "YELLOW"


    # ======================================================
    # DISPLAY SIGNALS
    # ======================================================

    draw_signal(
        frame,
        70,
        120,
        road_a_signal
    )


    draw_signal(
        frame,
        width - 70,
        120,
        road_b_signal
    )


    # ======================================================
    # DISPLAY TEXT
    # ======================================================

    cv2.putText(
        frame,
        "ROAD A",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )


    cv2.putText(
        frame,
        "Vehicles: "
        +
        str(road_a_count),
        (20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    cv2.putText(
        frame,
        "ROAD B",
        (middle + 20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )


    cv2.putText(
        frame,
        "Vehicles: "
        +
        str(road_b_count),
        (middle + 20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    status = (
        "GREEN ROAD: "
        +
        current_green
        +
        " | STATE: "
        +
        signal_state
    )


    cv2.putText(
        frame,
        status,
        (20, height - 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )


    # ======================================================
    # SHOW WINDOW
    # ======================================================

    cv2.imshow(
        WINDOW_TITLE,
        frame
    )

    key = cv2.waitKey(1) & 0xFF

    # Press Q or close window ('X' button) to exit
    if key == ord("q") or cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
        break


# ==========================================================
# CLEANUP
# ==========================================================

print("[INFO] Closing application...")
camera.release()
cv2.destroyAllWindows()
print("[INFO] Done.")