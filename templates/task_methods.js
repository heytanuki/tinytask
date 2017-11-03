function insert_task(grouping, task_description) {
    var data = {
        "description": task_description,
        "date_or_project": grouping
    };
    ajax_post("/tasklist/insert/", data, function(response) {
        // return new task data
    });
}

function advance_task_status(grouping, key) {
    ajax_post("/tasklist/advance/", load_request_data(grouping, key), function(response) {
        // return task data + status
    });
}

function un_do_task(grouping, key) {
    ajax_post("/tasklist/undo/", load_request_data(grouping, key), function() {return false;});
}

function delete_task(grouping, key) {
    ajax_post("/tasklist/delete/", load_request_data(grouping, key), function() {return false;});
}

function move_to_tomorrow(grouping, key) {
    var data = load_request_data(grouping, key);
    data.x_days = 1;
    ajax_post("/tasklist/moveto/", data, function() {return false;});
}

function load_request_data(grouping, key) {
    var data = {
        "date_or_project": grouping,
        "task_key": key
    };
    return data;
}

function ajax_get(url, data_in, callback) {
  var request = new XMLHttpRequest();
  request.onreadystatechange = function() {
    if (request.readyState == 4 && request.status == 200) {
      try {
        var data = JSON.parse(request.responseText);
      } catch(err) {
        console.log(err.message + " in " + request.responseText);
        return false;
      }
      callback(data);
    }
  };
  var url_params = Object.keys(data_in).map(function(prop) {
    return [prop, data_in[prop]].map(encodeURIComponent).join("=");
  }).join("&");
  var url_full = url + "?" + url_params
  request.open("GET", url_full, true);
  request.send();
}

function ajax_post(url, data_in, callback) {
  var request = new XMLHttpRequest();
  request.onreadystatechange = function() {
    if (request.readyState == 4 && request.status == 200) {
      try {
        var data = JSON.parse(request.responseText);
      } catch(err) {
        console.log("error time: " + request.responseText);
        return false;
      }
      callback(data);
    }
  };
  request.open('POST', url, true);
  request.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
  var url_params = Object.keys(data_in).map(function(prop) {
    return [prop, data_in[prop]].map(encodeURIComponent).join("=");
  }).join("&");
  request.send(url_params);
}