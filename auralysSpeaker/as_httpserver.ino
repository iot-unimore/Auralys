/* ************************************************************************** */
/* Webserver Control Functions                                                */
/* ************************************************************************** */

void httpServerSetup()
{
    if( WiFi.isConnected() && (WiFi.status() == WL_CONNECTED))
    {
        server.begin();
    }
}

void httpServerLoop()
{
    // if ( WiFi.status( ) == WL_CONNECTED )
    if( WiFi.isConnected() && (WiFi.status() == WL_CONNECTED))
    {
        volatile uint8_t cmd_ctrl = CTRL_CMD_NONE;
        volatile int16_t cmd_ctrl_position = 0;
        volatile int16_t req_content_length = -1;
        volatile int16_t header_content_length = -1;
        volatile int8_t rv = 0;

        client = server.accept();

        if( client )
        {
            httpCurrentTime = millis();
            httpPreviousTime = httpCurrentTime;
            req_content_length = -1;
            header_content_length = -1;

            LOG_MSGLN("\n +++++++++++++++++++\nNew Client.");

            if((httpCurrentTime - httpPreviousTime > httpTimeoutTime2S))
            {
                LOG_MSGLN(">>> TIMEOUT");
            }

            if( !(client.connected()))
            {
                LOG_MSGLN(">>> CLIENT NOT CONNECTED");
            }

            String currentLine = "";
            while( client.connected() && (httpCurrentTime - httpPreviousTime <= httpTimeoutTime2S))
            {
                httpCurrentTime = millis();
                if( client.available())
                {
                    char c = client.read();
                    // #ifdef DEBUG
                    // Serial.write( c );
                    // #endif
                    header += c;

                    if((c == '\n') || ((header_content_length > 0) && (header.length() >= header_content_length)))
                    {
                        // if the byte is a newline character
                        // if the current line is blank, you got two newline characters in a row.
                        // that's the end of the client HTTP request, so send a response (if there is n payload)
                        if((currentLine.length() == 0) &&
                           (header.indexOf("Content-Length:") >= 0) && (req_content_length < 0))
                        {
                            LOG_MSG("Got content length = ");

                            String val = "";
                            for(int i = 16 + header.indexOf("Content-Length: "); i < header.length(); i++ )
                            {
                                val += header.charAt(i);
                            }
                            LOG_MSGLN(val);

                            req_content_length = val.toInt();
                            header_content_length = header.length() + req_content_length;
                        }
                        // if the byte is a newline character
                        // if the current line is blank, you got two newline characters in a row.
                        // that's the end of the client HTTP request, so send a response (if there is n payload)
                        else if(((header.indexOf("Content-Length:") < 0) && (currentLine.length() == 0)) ||
                                (header.length() >= header_content_length))
                        {
                            cmd_ctrl = CTRL_CMD_NONE;

                            // HTTP headers always start with a response code (e.g. HTTP/1.1 200 OK)
                            // and a content-type so the client knows what's coming, then a blank line:
                            client.println("HTTP/1.1 200 OK");
                            client.println("Content-type:text/html");
                            client.println("Connection: close");
                            client.println();

                            LOG_MSGLN("===================================");
                            LOG_MSGLN("GOT HTTP CMD");
                            LOG_MSGLN(header);


                            /*
                             * select HTTP command
                             */
                            if((header.indexOf("GET /ctrl/stop") >= 0) || (header.indexOf("POST /ctrl/stop") >= 0))
                            {
                                LOG_MSGLN("Got request for system STOP");

                                cmd_ctrl = CTRL_CMD_STOP;
                                // getMksMotorStatus(mksMotorSlaveAddr);
                            }
                            if((header.indexOf("GET /ctrl/reset") >= 0) || (header.indexOf("POST /ctrl/reset") >= 0))
                            {
                                LOG_MSGLN("Got request for system RESET");
                                cmd_ctrl = CTRL_CMD_RESET;
                            }
                            if((header.indexOf("GET /ctrl/reboot") >= 0) || (header.indexOf("POST /ctrl/reboot") >= 0))
                            {
                                LOG_MSGLN("Got request for system REBOOT");
                                cmd_ctrl = CTRL_CMD_REBOOT;
                            }
                            else if( header.indexOf("GET /position/get") >= 0 )
                            {
                                cmd_ctrl = CTRL_CMD_POSITION_GET;
                                LOG_MSGLN("GET request for get-position");
                                displayCtrlMsgTemp("GET_POSITION", 5);
                            }
                            else if( header.indexOf("POST /position/set") >= 0 )
                            {
                                LOG_MSG("POST request for set-position: ");
                                cmd_ctrl = CTRL_CMD_POSITION_SET;

                                String post_param = "";
                                char p;

                                // position is 0(min)->359(max)
                                for(int i = 0; i < req_content_length; i++)
                                {
                                    p = header.charAt(header.length() - req_content_length + i);
                                    post_param += p;
                                }
                                // p = header.charAt(header.length() - req_content_length + 1);
                                // post_param += p;
                                // p = header.charAt(header.length() - req_content_length + 2);
                                // post_param += p;

                                // cmd_ctrl_position = post_param.toInt();

                                rv = mksCmdRequest(CTRL_CMD_POSITION_SET, post_param.toInt(), 0, 0, 0);
                            }
                            else if( header.indexOf("POST /position/zero/set") >= 0 )
                            {
                                LOG_MSG("POST request for set-zero-position: ");
                                cmd_ctrl = CTRL_CMD_ZERO_SET;
                                rv = mksCmdRequest(CTRL_CMD_ZERO_SET, 0, 0, 0, 0);
                            }
                            else if( header.indexOf("GET /status/get") >= 0 )
                            {
                                cmd_ctrl = CTRL_CMD_STATUS_GET;

                                LOG_MSG("POST request for status get: ");
                            }


                            /*
                             * prepare HTTP reply
                             */

                            if( !(header.indexOf("json")))
                            {
                                // Display the HTML web page
                                client.println("<!DOCTYPE html><html>");
                                client.println("<head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">");
                                client.println("<link rel=\"icon\" href=\"data:,\">");
                                // CSS to style the on/off buttons
                                // Feel free to change the background-color and font-size attributes to fit your preferences
                                // client.println("<style>html { font-family: Helvetica; display: inline-block; margin: 0px auto; text-align: center;}");
                                // client.println(".button { background-color: #4CAF50; border: none; color: white; padding: 16px 40px;");
                                // client.println("text-decoration: none; font-size: 30px; margin: 2px; cursor: pointer;}");
                                // client.println(".button2 {background-color: #555555;}</style></head>");
                                // Web Page Heading
                                client.println("<body>");
                            }
                            else if((CTRL_CMD_RESET == cmd_ctrl) || (CTRL_CMD_REBOOT == cmd_ctrl))
                            {
                                JsonDocument reply;
                                reply["syntax_ver"] = "0.1";
                                reply["error"] = 0;
                                serializeJsonPretty(reply, client);
                            }
                            else if((CTRL_CMD_POSITION_GET == cmd_ctrl) || (CTRL_CMD_SPEED_GET == cmd_ctrl) || (CTRL_CMD_STOP == cmd_ctrl))
                            {
                                JsonDocument reply;

                                if( CTRL_CMD_STOP == cmd_ctrl )
                                {
                                    // motion_stop( );
                                }

                                reply["syntax_ver"] = "0.1";
                                reply["error"] = 0;
                                // reply[ "position" ] = position;
                                // reply[ "position_begin" ] = position_begin;
                                // reply[ "position_end" ] = position_end;
                                // reply[ "motion" ] = motion_status_ctrl & 0x01;
                                // reply[ "motion_direction" ] = ( motion_status_ctrl & 0x02 ) >> 1;
                                // reply[ "motion_speed" ] = motion_speed; // motion_compute_speed (position, position_begin, position_end);

                                serializeJsonPretty(reply, client);
                            }
                            else if( CTRL_CMD_POSITION_SET == cmd_ctrl )
                            {
                                JsonDocument reply;
                                reply["syntax_ver"] = "0.1";
                                reply["error"] = rv;
                                // reply[ "position" ] = position;
                                // reply[ "position_begin" ] = position_begin;
                                // reply[ "position_end" ] = position_end;
                                // reply[ "motion" ] = motion_status_ctrl & 0x01;
                                // reply[ "motion_direction" ] = ( motion_status_ctrl & 0x02 ) >> 1;
                                // reply[ "motion_speed" ] = motion_speed; // motion_compute_speed (position, position_begin, position_end);


                                // SANITY CHECK
                                // if((cmd_ctrl_position >= 0) && (cmd_ctrl_position < 360))
                                // {
                                //// position_end = cmd_ctrl_position;
                                // reply["error"] = 0;
                                // reply["position_end"] = cmd_ctrl_position; // position_end;
                                // }

                                serializeJsonPretty(reply, client);
                            }
                            else if( CTRL_CMD_ZERO_SET == cmd_ctrl )
                            {
                                JsonDocument reply;
                                reply["syntax_ver"] = "0.1";
                                reply["error"] = rv;
                                serializeJsonPretty(reply, client);
                            }
                            else if( CTRL_CMD_STATUS_GET == cmd_ctrl )
                            {
                                JsonDocument reply;
                                reply["syntax_ver"] = "0.1";
                                reply["error"] = rv;
                                reply["status"] = mksMotorCmdQueue[0].status;

                                serializeJsonPretty(reply, client);
                            }
                            else
                            {
                                /* default to error */

                                JsonDocument reply;
                                reply["syntax_ver"] = "0.1";
                                reply["error"] = 1;
                                serializeJsonPretty(reply, client);
                            }

                            if( !(header.indexOf(".json")))
                            {
                                client.println("</body></html>");
                            }

                            // The HTTP response ends with another blank line
                            client.println();
                            client.println();

                            /* flush client request */
                            client.clear();

                            // clear web request
                            header = "";

                            /* special case: handle reset request after reply */
                            if( CTRL_CMD_RESET == cmd_ctrl )
                            {
                                LOG_MSGLN("Resetting...");
                                client.stop();
                                delay(300);
                                bspReset();
                                delay(100);
                                bspReboot();
                            }

                            if( CTRL_CMD_REBOOT == cmd_ctrl )
                            {
                                LOG_MSGLN("Rebooting...");
                                client.stop();
                                delay(300);
                                bspReboot();
                            }

                            // Break out of the while loop
                            break;
                        }
                        else
                        { // if you got a newline, then clear currentLine
                            currentLine = "";
                        }
                    }
                    else if( c != '\r' )
                    { // if you got anything else but a carriage return character,
                        currentLine += c; // add it to the end of the currentLine
                    }
                }
            } // while client.connected

            client.clear();
            client.stop();
        }
    }
}
