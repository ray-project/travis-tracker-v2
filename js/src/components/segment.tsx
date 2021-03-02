import React from "react";
import { Tooltip } from "antd";
import { SiteCommitTooltip } from "../interface";
import "./segment.css";

interface Prop {
  commits: Array<SiteCommitTooltip>;
}

const SegmentedBar: React.FC<Prop> = ({ commits }) => {
  return (
    <div style={{ display: "flex", width: "90%", margin: "0 auto" }}>
      {commits.map((c) => {
        let className = "";
        if (c.num_failed === null) {
          className = "item not-found";
        } else if (c.num_failed === 0) {
          if (c.num_flaky === 0) {
            className = "item";
          } else {
            className = `item flaky`;

          }
        } else {
          className = `item failed`;
        }

        return (
          <Tooltip
            color="#FFFFFF"
            title={
              <p>
                <img
                  src={c.author_avatar}
                  height="16px"
                  style={{ paddingRight: "8px" }}
                />
                <a href={c.commit_url}>{c.message}</a>
              </p>
            }
          >
            <div className={className} />
          </Tooltip>
        );
      })}
    </div>
  );
};

export default SegmentedBar;
