import sys
import csv

def normalize_timestamp(input_filename, output_filename):
    """
    Reads a CSV file, combines the first two columns (date and time) 
    into a single timestamp, changes date format from YYYY/MM/DD to YYYY-MM-DD,
    and writes the result to a new CSV file.

    Args:
        input_filename (str): Path to the input CSV file.
        output_filename (str): Path to the output CSV file.
    """
    lines_processed = 0
    print(f"Starting timestamp normalization...")
    print(f"Input file: {input_filename}")
    print(f"Output file: {output_filename}")

    try:
        with open(input_filename, 'r', encoding='utf-8', newline='') as infile, \
             open(output_filename, 'w', encoding='utf-8', newline='') as outfile:
            
            reader = csv.reader(infile)
            writer = csv.writer(outfile)

            for i, row in enumerate(reader):
                if len(row) >= 2:
                    date_part = row[0].strip().replace('/', '-') # Replace slashes with dashes
                    time_part = row[1].strip()
                    timestamp = f"{date_part} {time_part}"
                    
                    # Create the new row with the combined timestamp and the rest of the data
                    new_row = [timestamp] + [col.strip() for col in row[2:]]
                    writer.writerow(new_row)
                    lines_processed += 1
                else:
                    # Handle potentially empty or malformed lines if necessary
                    print(f"Warning: Skipping malformed line {i+1}: {row}")
                    continue # Skip writing this line

                if (i + 1) % 1000000 == 0: # Print progress every million lines
                     print(f"Processed {i + 1} lines...")

        print(f"Finished processing.")
        print(f"Total lines written to {output_filename}: {lines_processed}")

    except FileNotFoundError:
        print(f"Error: Input file '{input_filename}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred during processing line {lines_processed + 1}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # --- Configuration ---
    INPUT_FILE = "BTCUSDT_6M-04-21.txt"
    OUTPUT_FILE = "BTCUSDT_PERP_BINANCE_normalized.txt"
    # --- End Configuration ---

    normalize_timestamp(INPUT_FILE, OUTPUT_FILE) 