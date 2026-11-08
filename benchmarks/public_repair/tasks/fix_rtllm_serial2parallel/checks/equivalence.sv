module tb();
	reg clk,rst_n;
	reg din_serial,din_valid;
	wire dout_valid;
	wire[7:0]dout_parallel;
 
	always #5 clk = ~clk;
  integer error = 0;
  integer wait_count = 0;

  task wait_dout_valid;
  begin
    wait_count = 0;
    while(dout_valid == 0 && wait_count < 20) begin
      #5;
      wait_count = wait_count + 1;
    end
    if (dout_valid == 0) begin
      error = error + 1;
      $display("Timeout waiting for dout_valid");
    end
  end
  endtask

	initial begin
		clk  <= 1'b0;
		rst_n <= 1'b0;
		#12
		rst_n <= 1'b1;
		din_valid  <= 1'b1;

		din_serial <= 1'b1; #10;
		din_serial <= 1'b1; #10;
		din_serial <= 1'b1; #10;
		din_serial <= 1'b1; #10;
    error = (dout_valid == 0) ?error:error+1;
		din_serial <= 1'b0; #10;
    din_serial <= 1'b0; #10;
    din_serial <= 1'b0; #10;
    din_serial <= 1'b0; #10;
    wait_dout_valid;
    // $display("%b",dout_parallel);
    error = (dout_parallel == 8'b11110000) ?error:error+1;
    
    din_valid  <= 1'b0; 
		#30;
		din_valid  <= 1'b1;

    din_serial <= 1'b1; #10
    din_serial <= 1'b1; #10
    din_serial <= 1'b0; #10
		din_serial <= 1'b0; #10
    error = (dout_valid == 0) ?error:error+1;
		din_serial <= 1'b0; #10
		din_serial <= 1'b0; #10
		din_serial <= 1'b1; #10
		din_serial <= 1'b1; #20
		din_valid  <= 1'b0;
    wait_dout_valid;
    // $display("%b",dout_parallel);
    error = (dout_parallel == 8'b11000011) ?error:error+1;
		#10
    error = (dout_valid == 0) ?error:error+1;
    #10

    if (error == 0) begin
        $display("HWBENCH_PASS");
    end
    else begin
    $fatal(1, "Test completed with %0d failures ===========", error);
    end
		$finish;
	end 
	serial2parallel u0(
    .clk           (clk)           ,
    .rst_n          (rst_n)          ,
    .din_serial    (din_serial)    ,
    .dout_parallel (dout_parallel) ,
    .din_valid     (din_valid)     ,
    .dout_valid    (dout_valid)
	);  
endmodule
