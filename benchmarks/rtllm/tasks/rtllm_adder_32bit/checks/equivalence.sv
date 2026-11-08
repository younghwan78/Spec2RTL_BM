`timescale  1ns/1ns
module adder32_tb;
integer hwb_seed = 1;
initial if (!$value$plusargs("SEED=%d", hwb_seed)) hwb_seed = 1;

  
  reg [31:0] A;
  reg [31:0] B;
  wire [31:0] S;
  wire C32;
  
  integer i; 
  integer error = 0; 
  reg [33:0] expected_sum; 
  
  // Instantiate the module
  adder_32bit uut (
    .A(A), 
    .B(B), 
    .S(S), 
    .C32(C32)
  );
  
  // Randomize inputs and check output
  initial begin
    for (i = 0; i < 100; i = i + 1) begin
      A = $random(hwb_seed);
      B = $random(hwb_seed);
      #10; 
      // Calculate expected sum and carry out
      expected_sum = A + B;
      error = (S !== expected_sum[31:0] || C32 !== expected_sum[32]) ? error+1 : error; 
    end
    if (error == 0) begin
            $display("HWBENCH_PASS");
    end
    else begin
    $fatal(1, "Test completed with %d /100 failures===========", error);
    end
  end

endmodule