import React from "react";
import { Tooltip } from "antd";
import { SiteCommitTooltip } from "../interface";
import "./segment.css";

interface Prop {
  commits: Array<SiteCommitTooltip>;
  prefix: string;
}

const SegmentedBar: React.FC<Prop> = ({ commits, prefix }) => {
  return (
    <div style={{ display: "flex", width: "90%", margin: "0 auto" }}>
      {commits.map((c) => {
        let className = "";
        if (c.num_failed === null) {
          className = "item not-found";
        } else if (c.num_failed === 0 && c.num_flaky === 0) {
          className = "item";
        } else if (c.num_flaky > 0) {
          className = `item flaky`;
        } else {
          className = `item failed`;
        }

        return (
          <Tooltip
            key={c.commit_url}
            color="#FFFFFF"
            title={
              <p>
                <img
                  src={c.author_avatar}
                  height="16px"
                  style={{ paddingRight: "8px" }}
                />
                <a href={c.commit_url}>
                  {prefix} {c.message}
                </a>
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
