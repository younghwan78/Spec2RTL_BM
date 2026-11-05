module choose_grant(input[1:0]req,input pref,output[1:0]grant);assign grant=req==3?(pref?2'b10:2'b01):req;endmodule
