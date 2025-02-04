import spidr4.io as s4io
import gzip
import os

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Open the test-screen data
    with gzip.open(os.path.join(script_dir, "testscreen-8192-210505-122755-1.dat.gz"), "rb") as stream:
        # Open the file-stream
        for chunk in s4io.Spidr4FileStream(stream):
            print(f"Chunk {chunk.header}")
            # If it is NOT pixel data:
            if chunk.group not in (s4io.GROUP_TPX4DATA_BOT, s4io.GROUP_TPX4DATA_TOP, s4io.GROUP_TPX4DATA):
                continue
            # Otherwise, show all pixels this chunk
            print("Timepix4 pixel data:")
            for data in chunk.data64b():
                print(f"- {data:016x}")
