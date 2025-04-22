import sys

def filter_file_by_line(input_filename, output_filename, start_line_number):
    """
    Reads an input file and writes lines from start_line_number onwards 
    to an output file.

    Args:
        input_filename (str): Path to the input text file.
        output_filename (str): Path to the output text file.
        start_line_number (int): The 1-based line number to start keeping lines from.
    """
    start_index = start_line_number - 1  # Convert to 0-based index
    lines_written = 0
    
    print(f"Starting filtering process...")
    print(f"Input file: {input_filename}")
    print(f"Output file: {output_filename}")
    print(f"Keeping lines from number {start_line_number} onwards.")

    try:
        with open(input_filename, 'r', encoding='utf-8') as infile, \
             open(output_filename, 'w', encoding='utf-8') as outfile:
            
            for i, line in enumerate(infile):
                if i >= start_index:
                    outfile.write(line)
                    lines_written += 1
                if (i + 1) % 1000000 == 0: # Print progress every million lines
                     print(f"Processed {i + 1} lines...")

        print(f"Finished processing.")
        print(f"Total lines written to {output_filename}: {lines_written}")

    except FileNotFoundError:
        print(f"Error: Input file '{input_filename}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # --- Configuration ---
    INPUT_FILE = "BTCUSDT_PERP_BINANCE.txt" 
    OUTPUT_FILE = "BTCUSDT_PERP_BINANCE_filtered.txt"
    START_LINE = 7006833 
    # --- End Configuration ---

    filter_file_by_line(INPUT_FILE, OUTPUT_FILE, START_LINE) 